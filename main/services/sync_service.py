import json
import logging
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import uuid as uuid_module

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.apps import apps

logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        if isinstance(obj, uuid_module.UUID):
            return str(obj)
        return super().default(obj)

@dataclass
class SyncRecord:
    model_name: str
    uuid: str
    data: dict
    created_at: str
    attempts: int = 0
    last_error: str = None
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class SyncStatus:
    is_online: bool
    last_sync: Optional[str]
    pending_count: int
    failed_count: int
    last_error: Optional[str]


class SyncQueue:
    _lock = threading.Lock()
    
    @classmethod
    def _get_queue_path(cls) -> Path:
        return Path(getattr(settings, 'SYNC_QUEUE_FILE', 'sync_queue.json'))
    
    @classmethod
    def _read_queue(cls) -> List[SyncRecord]:
        path = cls._get_queue_path()
        try:
            if path.exists():
                content = path.read_text(encoding='utf-8').strip()
                if content:
                    data = json.loads(content)
                    return [SyncRecord.from_dict(d) for d in data]
        except Exception as e:
            logger.error(f"Error reading sync queue: {e}")
            try:
                if path.exists():
                    backup_path = path.with_suffix('.json.corrupted')
                    path.rename(backup_path)
                    logger.warning(f"Corrupted queue backed up to {backup_path}")
            except:
                pass
        return []
    
    @classmethod
    def _write_queue(cls, records: List[SyncRecord]):
        path = cls._get_queue_path()
        try:
            data = []
            for r in records:
                record_dict = r.to_dict()
                if 'data' in record_dict and isinstance(record_dict['data'], dict):
                    serialized = json.dumps(record_dict['data'], cls=DecimalEncoder)
                    record_dict['data'] = json.loads(serialized)
                data.append(record_dict)
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        except Exception as e:
            logger.error(f"Error writing sync queue: {e}")
    
    @classmethod
    def add(cls, record: SyncRecord):
        with cls._lock:
            records = cls._read_queue()
            existing_idx = None
            for i, r in enumerate(records):
                if r.uuid == record.uuid and r.model_name == record.model_name:
                    existing_idx = i
                    break
            
            if existing_idx is not None:
                records[existing_idx] = record
            else:
                records.append(record)
            
            cls._write_queue(records)
            logger.debug(f"Queued: {record.model_name} {record.uuid}")
    
    @classmethod
    def get_batch(cls, limit: int = 100) -> List[SyncRecord]:
        with cls._lock:
            records = cls._read_queue()
            records.sort(key=lambda r: r.created_at)
            return records[:limit]
    
    @classmethod
    def remove(cls, uuids: List[str]):
        with cls._lock:
            records = cls._read_queue()
            records = [r for r in records if r.uuid not in uuids]
            cls._write_queue(records)
    
    @classmethod
    def mark_failed(cls, uuid: str, error: str):
        with cls._lock:
            records = cls._read_queue()
            for r in records:
                if r.uuid == uuid:
                    r.attempts += 1
                    r.last_error = error
                    break
            cls._write_queue(records)
    
    @classmethod
    def count(cls) -> Tuple[int, int]:
        records = cls._read_queue()
        failed = sum(1 for r in records if r.attempts > 0)
        return len(records), failed
    
    @classmethod
    def clear(cls):
        with cls._lock:
            cls._write_queue([])


class SyncStatusTracker:
    _status_file = Path('data/sync_status.json')
    
    @classmethod
    def _read(cls) -> dict:
        try:
            if cls._status_file.exists():
                with open(cls._status_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    @classmethod
    def _write(cls, data: dict):
        try:
            with open(cls._status_file, 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    @classmethod
    def update(cls, **kwargs):
        data = cls._read()
        data.update(kwargs)
        data['updated_at'] = timezone.now().isoformat()
        cls._write(data)
    
    @classmethod
    def get(cls) -> dict:
        return cls._read()


class SyncService:
    SYNCABLE_MODELS = [
        'main.User',
        'main.Category',
        'main.Product',
        'main.DeliveryPerson',
        'main.Order',
        'main.OrderItem',
        'main.CashRegister',
        'main.Inkassa',
    ]
    
    @classmethod
    def is_enabled(cls) -> bool:
        return getattr(settings, 'SYNC_ENABLED', False)
    
    @classmethod
    def is_local_mode(cls) -> bool:
        return getattr(settings, 'DEPLOYMENT_MODE', 'local') == 'local'
    
    @classmethod
    def get_cloud_url(cls) -> str:
        base_url = getattr(settings, 'CLOUD_SYNC_URL', '').rstrip('/')
        return f"{base_url}/"
    
    @classmethod
    def get_auth_headers(cls) -> dict:
        token = getattr(settings, 'CLOUD_SYNC_TOKEN', '')
        branch_id = getattr(settings, 'BRANCH_ID', 'unknown')
        return {
            'Authorization': f'Branch {token}',
            'X-Branch-ID': branch_id,
            'Content-Type': 'application/json',
        }

    @classmethod
    def queue_record(cls, instance):
        if not cls.is_enabled() or not cls.is_local_mode():
            return
        
        try:
            model_name = f"{instance._meta.app_label}.{instance._meta.model_name}"
            
            record = SyncRecord(
                model_name=model_name,
                uuid=str(instance.uuid),
                data=instance.to_sync_dict(),
                created_at=timezone.now().isoformat(),
            )
            
            SyncQueue.add(record)
            
        except Exception as e:
            logger.error(f"Error queuing record for sync: {e}")

    @classmethod
    def check_connection(cls) -> bool:
        try:
            response = requests.get(
                f"{cls.get_cloud_url()}/health",
                headers=cls.get_auth_headers(),
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    @classmethod
    def sync_now(cls) -> Dict[str, Any]:
        if not cls.is_enabled():
            return {'success': False, 'message': 'Sync not enabled'}
        
        if not cls.is_local_mode():
            return {'success': False, 'message': 'Sync only available in local mode'}
        
        result = {
            'success': True,
            'synced': 0,
            'failed': 0,
            'errors': [],
            'started_at': timezone.now().isoformat(),
        }
        
        if not cls.check_connection():
            SyncStatusTracker.update(
                is_online=False,
                last_error='Cannot reach cloud server'
            )
            return {
                'success': False,
                'message': 'Cannot reach cloud server',
                'offline': True
            }
        
        SyncStatusTracker.update(is_online=True)
        batch_size = getattr(settings, 'SYNC_BATCH_SIZE', 100)
        pending = SyncQueue.get_batch(batch_size)
        
        if not pending:
            return {'success': True, 'message': 'Nothing to sync', 'synced': 0}
        
        by_model = defaultdict(list)
        for record in pending:
            by_model[record.model_name].append(record)
        
        synced_uuids = []

        MODEL_ORDER = [
            'main.user',
            'main.category', 
            'main.deliveryperson',
            'main.product',
            'main.order',
            'main.orderitem',
            'main.cashregister',
            'main.inkassa',
        ]

        sorted_models = sorted(
            by_model.keys(),
            key=lambda m: MODEL_ORDER.index(m.lower()) if m.lower() in MODEL_ORDER else 999
        )
        
        for model_name in sorted_models:
            records = by_model[model_name]
            try:
                sync_result = cls._sync_model_batch(model_name, records)
                
                if sync_result['success']:
                    synced_uuids.extend(sync_result['synced_uuids'])
                    result['synced'] += len(sync_result['synced_uuids'])
                else:
                    result['failed'] += len(records)
                    result['errors'].append(f"{model_name}: {sync_result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                result['failed'] += len(records)
                result['errors'].append(f"{model_name}: {str(e)}")
                logger.exception(f"Error syncing {model_name}")
        
        if synced_uuids:
            SyncQueue.remove(synced_uuids)
        
        SyncStatusTracker.update(
            last_sync=timezone.now().isoformat(),
            last_error=result['errors'][0] if result['errors'] else None
        )
        
        result['completed_at'] = timezone.now().isoformat()
        
        return result
    
    @classmethod
    def _sync_model_batch(cls, model_name: str, records: List[SyncRecord]) -> dict:
        try:
            payload = {
                'model': model_name,
                'branch_id': getattr(settings, 'BRANCH_ID', 'unknown'),
                'records': [r.data for r in records],
            }
            
            response = requests.post(
                f"{cls.get_cloud_url()}/receive",
                headers=cls.get_auth_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'synced_uuids': [r.uuid for r in records],
                    'cloud_response': data
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Request timeout'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Connection failed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def get_status(cls) -> SyncStatus:
        pending, failed = SyncQueue.count()
        status_data = SyncStatusTracker.get()
        
        return SyncStatus(
            is_online=status_data.get('is_online', False),
            last_sync=status_data.get('last_sync'),
            pending_count=pending,
            failed_count=failed,
            last_error=status_data.get('last_error')
        )
    
    @classmethod
    def get_pending_summary(cls) -> Dict[str, int]:
        records = SyncQueue.get_batch(1000)
        summary = defaultdict(int)
        for r in records:
            summary[r.model_name] += 1
        return dict(summary)


class CloudReceiverService:
    @classmethod
    def is_branch_authorized(cls, branch_token: str) -> bool:
        allowed = getattr(settings, 'ALLOWED_BRANCH_TOKENS', [])
        return branch_token in allowed
    
    @classmethod
    def receive_batch(cls, model_name: str, branch_id: str, records: List[dict]) -> dict:
        result = {
            'success': True,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': []
        }
        
        try:
            app_label, model = model_name.lower().split('.')
            ModelClass = apps.get_model(app_label, model)
            
            print(f"[SYNC] Processing {len(records)} records for {model_name}")
            
            for record_data in records:
                try:
                    record_uuid = record_data.get('uuid')
                    print(f"[SYNC] Processing record UUID: {record_uuid}")
                    print(f"[SYNC] Record data: {record_data}")
                    
                    instance, action = cls._create_or_update_record(ModelClass, record_data, branch_id)
                    
                    print(f"[SYNC] Result: {action} - Instance ID: {instance.id if instance else 'None'}")
                    
                    if action == 'created':
                        result['created'] += 1
                    elif action == 'updated':
                        result['updated'] += 1
                    else:
                        result['skipped'] += 1
                        
                except Exception as e:
                    import traceback
                    error_msg = f"Record {record_data.get('uuid', '?')}: {str(e)}"
                    print(f"[SYNC ERROR] {error_msg}")
                    print(f"[SYNC ERROR] Traceback: {traceback.format_exc()}")
                    result['errors'].append(error_msg)
            
        except Exception as e:
            import traceback
            result['success'] = False
            result['errors'].append(str(e))
            print(f"[SYNC ERROR] Batch error: {str(e)}")
            print(f"[SYNC ERROR] Traceback: {traceback.format_exc()}")
        
        print(f"[SYNC] Final result: {result}")
        return result
    
    @classmethod
    def _create_or_update_record(cls, ModelClass, data: dict, branch_id: str):
        from django.utils import timezone
        from decimal import Decimal
        from dateutil import parser as date_parser
        
        data = data.copy()
        
        uuid_val = data.pop('uuid', None)
        if not uuid_val:
            raise ValueError("Record missing UUID")
        
        sync_version = data.pop('sync_version', 1)
        is_deleted = data.pop('is_deleted', False)
        incoming_branch = data.pop('branch_id', branch_id)
        
        data.pop('user_uuid', None)
        data.pop('cashier_uuid', None)
        data.pop('delivery_person_uuid', None)
        data.pop('category_uuid', None)
        data.pop('order_uuid', None)
        data.pop('product_uuid', None)
        
        model_fields = {f.name for f in ModelClass._meta.get_fields() if hasattr(f, 'column')}
        
        cleaned_data = {}
        for key, value in data.items():
            if key not in model_fields:
                continue
                
            if value is None:
                cleaned_data[key] = value
                continue
            
            try:
                field = ModelClass._meta.get_field(key)
                
                if field.get_internal_type() == 'DecimalField':
                    cleaned_data[key] = Decimal(str(value)) if value else Decimal('0')
                elif field.get_internal_type() in ('DateTimeField', 'DateField'):
                    if isinstance(value, str) and value:
                        cleaned_data[key] = date_parser.parse(value)
                    else:
                        cleaned_data[key] = value
                elif field.get_internal_type() == 'ForeignKey':
                    continue
                else:
                    cleaned_data[key] = value
            except Exception as e:
                print(f"[SYNC] Warning: Could not process field {key}: {e}")
                cleaned_data[key] = value
        
        try:
            instance = ModelClass.objects.get(uuid=uuid_val)
            
            if sync_version >= instance.sync_version:
                for key, value in cleaned_data.items():
                    setattr(instance, key, value)
                instance.sync_version = sync_version
                instance.is_deleted = is_deleted
                instance.synced_at = timezone.now()
                instance.branch_id = incoming_branch
                instance.save()
                return instance, 'updated'
            else:
                return instance, 'skipped'
            
        except ModelClass.DoesNotExist:
            instance = ModelClass(
                uuid=uuid_val,
                sync_version=sync_version,
                is_deleted=is_deleted,
                branch_id=incoming_branch,
            )
            for key, value in cleaned_data.items():
                setattr(instance, key, value)
            
            instance.save()
            return instance, 'created'
    
    @classmethod
    def _broadcast_update(cls, model_name: str, branch_id: str, result: dict):
        pass


class SyncWorker:
    _running = False
    _thread = None
    
    @classmethod
    def start(cls):
        if cls._running:
            return
        
        cls._running = True
        cls._thread = threading.Thread(target=cls._run_loop, daemon=True)
        cls._thread.start()
        logger.info("Sync worker started")
    
    @classmethod
    def stop(cls):
        cls._running = False
        if cls._thread:
            cls._thread.join(timeout=5)
        logger.info("Sync worker stopped")
    
    @classmethod
    def _run_loop(cls):
        interval = getattr(settings, 'SYNC_INTERVAL', 30)
        retry_interval = getattr(settings, 'SYNC_RETRY_INTERVAL', 60)
        
        while cls._running:
            try:
                result = SyncService.sync_now()
                
                if result.get('offline'):
                    time.sleep(retry_interval)
                else:
                    time.sleep(interval)
                    
            except Exception as e:
                logger.exception("Error in sync loop")
                time.sleep(retry_interval)


def start_sync_worker_on_ready():
    if SyncService.is_enabled() and SyncService.is_local_mode():
        threading.Timer(5.0, SyncWorker.start).start()