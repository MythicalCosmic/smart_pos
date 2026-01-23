"""
Sync API Views

Endpoints:
- /api/sync/health - Health check
- /api/sync/receive - Cloud receives data from branches
- /api/sync/status - Local checks sync status
- /api/sync/trigger - Local triggers manual sync
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

logger = logging.getLogger(__name__)


class SyncHealthView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        return Response({
            'status': 'ok',
            'mode': getattr(settings, 'DEPLOYMENT_MODE', 'unknown'),
            'sync_enabled': getattr(settings, 'SYNC_ENABLED', False),
        })


class SyncReceiveView(APIView):
    authentication_classes = []  
    permission_classes = []
    
    def post(self, request):
        # DEBUG - see what's coming in
        print("="*50)
        print("RECEIVED SYNC REQUEST:")
        print(f"Headers: {dict(request.headers)}")
        print(f"Data: {request.data}")
        print("="*50)
        
        if getattr(settings, 'DEPLOYMENT_MODE', '') != 'cloud':
            return Response(
                {'error': 'Sync receive only available on cloud server'},
                status=status.HTTP_403_FORBIDDEN
            )
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Branch '):
            return Response(
                {'error': 'Invalid authorization'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        branch_token = auth_header[7:]
        branch_id = request.headers.get('X-Branch-ID', 'unknown')
        
        from main.services.sync_service import CloudReceiverService
        
        if not CloudReceiverService.is_branch_authorized(branch_token):
            logger.warning(f"Unauthorized sync attempt from branch: {branch_id}")
            return Response(
                {'error': 'Branch not authorized'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        model_name = request.data.get('model')
        records = request.data.get('records', [])
        
        if not model_name or not records:
            return Response(
                {'error': 'Missing model or records'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = CloudReceiverService.receive_batch(model_name, branch_id, records)
        
        logger.info(f"Sync received from {branch_id}: {model_name} - "
                   f"created={result['created']}, updated={result['updated']}")
        
        return Response(result)



class SyncStatusView(APIView):    
    def get(self, request):
        from main.services.sync_service import SyncService
        
        if not SyncService.is_enabled():
            return Response({
                'enabled': False,
                'message': 'Sync not enabled'
            })
        
        sync_status = SyncService.get_status()
        pending_summary = SyncService.get_pending_summary()
        
        return Response({
            'enabled': True,
            'mode': getattr(settings, 'DEPLOYMENT_MODE', 'unknown'),
            'branch_id': getattr(settings, 'BRANCH_ID', 'unknown'),
            'is_online': sync_status.is_online,
            'last_sync': sync_status.last_sync,
            'pending_count': sync_status.pending_count,
            'failed_count': sync_status.failed_count,
            'last_error': sync_status.last_error,
            'pending_by_model': pending_summary,
        })


class SyncTriggerView(APIView):
    def post(self, request):
        from main.services.sync_service import SyncService
        
        if not SyncService.is_enabled():
            return Response({
                'success': False,
                'message': 'Sync not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not SyncService.is_local_mode():
            return Response({
                'success': False,
                'message': 'Manual sync only available in local mode'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        result = SyncService.sync_now()
        
        return Response(result)


class SyncQueueView(APIView):    
    def get(self, request):
        from main.services.sync_service import SyncQueue
        
        records = SyncQueue.get_batch(100)
        
        return Response({
            'count': len(records),
            'records': [
                {
                    'model': r.model_name,
                    'uuid': r.uuid,
                    'created_at': r.created_at,
                    'attempts': r.attempts,
                    'last_error': r.last_error,
                }
                for r in records
            ]
        })
    
    def delete(self, request):
        from main.services.sync_service import SyncQueue
        
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        
        if not confirm:
            return Response({
                'error': 'Add ?confirm=true to clear queue',
                'warning': 'This will delete all pending sync data!'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        SyncQueue.clear()
        
        return Response({
            'success': True,
            'message': 'Sync queue cleared'
        })
def get_sync_urls():
    from django.urls import path
    
    return [
        path('health', SyncHealthView.as_view(), name='sync-health'),
        path('receive', SyncReceiveView.as_view(), name='sync-receive'),
        path('status', SyncStatusView.as_view(), name='sync-status'),
        path('trigger', SyncTriggerView.as_view(), name='sync-trigger'),
        path('queue', SyncQueueView.as_view(), name='sync-queue'),
    ]
