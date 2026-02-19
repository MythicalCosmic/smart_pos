from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from stock.services import (
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    StockSettingsService, AlertConfigService,
    StockLocationService, StockUnitService, StockItemUnitService,
    StockCategoryService, StockItemService,
    StockLevelService, StockTransactionService, StockBatchService,
    SupplierService, SupplierStockItemService,
    PurchaseOrderService, PurchaseOrderItemService, PurchaseReceivingService,
    RecipeService, RecipeIngredientService, RecipeStepService,
    ProductionOrderService,
    StockTransferService, StockTransferItemService,
    StockCountService, StockCountItemService, VarianceReasonCodeService,
    ProductStockLinkService, ProductComponentService,
    OrderStockService,
)

def error_response(message: str, code: str = "error", status: int = 400, details: dict = None):
    data = {"success": False, "error": {"code": code, "message": message}}
    if details:
        data["error"]["details"] = details
    return JsonResponse(data, status=status)


def handle_service_error(e: Exception):
    if isinstance(e, ValidationError):
        return error_response(str(e), "validation_error", 400, {"field": e.field})
    elif isinstance(e, NotFoundError):
        return error_response(str(e), "not_found", 404)
    elif isinstance(e, InsufficientStockError):
        return error_response(str(e), "insufficient_stock", 400, e.details)
    elif isinstance(e, BusinessRuleError):
        return error_response(str(e), "business_rule", 400)
    else:
        return error_response(str(e), "server_error", 500)


class BaseStockView(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get_json_body(self, request):
        try:
            return json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return {}
    
    def get_user_id(self, request):
        if request.user.is_authenticated:
            return request.user.id
        return None
    
    def success(self, data: dict, status: int = 200):
        return JsonResponse({"success": True, **data}, status=status)


# ==================== SETTINGS ====================

class StockSettingsView(BaseStockView):
    
    def get(self, request):
        try:
            result = StockSettingsService.get_all()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request):
        try:
            data = self.get_json_body(request)
            result = StockSettingsService.update(**data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockSettingsToggleView(BaseStockView):
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            module = data.get("module", "stock")
            enabled = data.get("enabled", True)
            
            if module == "stock":
                result = StockSettingsService.toggle_stock(enabled)
            else:
                result = StockSettingsService.toggle_module(module, enabled)
            
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class AlertConfigListView(BaseStockView):
    
    def get(self, request):
        try:
            result = AlertConfigService.get_all()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = AlertConfigService.create_or_update(
                alert_type=data["alert_type"],
                **{k: v for k, v in data.items() if k != "alert_type"}
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)



class LocationListView(BaseStockView):

    
    def get(self, request):
        try:
            location_type = request.GET.get("type")
            parent_id = request.GET.get("parent_id")
            tree = request.GET.get("tree", "false").lower() == "true"
            
            if tree:
                result = StockLocationService.get_tree()
            else:
                result = StockLocationService.list(
                    type_filter=location_type,
                    parent_id=int(parent_id) if parent_id else None
                )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = StockLocationService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class LocationDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/locations/<id>/"""
    
    def get(self, request, location_id):
        try:
            result = StockLocationService.get(location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, location_id):
        try:
            data = self.get_json_body(request)
            result = StockLocationService.update(location_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, location_id):
        try:
            result = StockLocationService.deactivate(location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class LocationSetDefaultView(BaseStockView):
    """POST /api/stock/locations/<id>/set-default/"""
    
    def post(self, request, location_id):
        try:
            result = StockLocationService.set_default(location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== UNITS ====================

class UnitListView(BaseStockView):
    """GET/POST /api/stock/units/"""
    
    def get(self, request):
        try:
            unit_type = request.GET.get("type")
            if unit_type:
                result = StockUnitService.get_by_type(unit_type)
            else:
                result = StockUnitService.list()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = StockUnitService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class UnitDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/units/<id>/"""
    
    def get(self, request, unit_id):
        try:
            result = StockUnitService.get(unit_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, unit_id):
        try:
            data = self.get_json_body(request)
            result = StockUnitService.update(unit_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, unit_id):
        try:
            result = StockUnitService.deactivate(unit_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class UnitConvertView(BaseStockView):
    """POST /api/stock/units/convert/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result, details = StockUnitService.convert(
                quantity=data["quantity"],
                from_unit_id=data["from_unit_id"],
                to_unit_id=data["to_unit_id"]
            )
            return self.success({"result": str(result), "details": details})
        except Exception as e:
            return handle_service_error(e)


# ==================== CATEGORIES ====================

class CategoryListView(BaseStockView):
    """GET/POST /api/stock/categories/"""
    
    def get(self, request):
        try:
            tree = request.GET.get("tree", "false").lower() == "true"
            category_type = request.GET.get("type")
            
            if tree:
                result = StockCategoryService.get_tree()
            elif category_type:
                result = StockCategoryService.get_by_type(category_type)
            else:
                result = StockCategoryService.list()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = StockCategoryService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class CategoryDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/categories/<id>/"""
    
    def get(self, request, category_id):
        try:
            result = StockCategoryService.get(category_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, category_id):
        try:
            data = self.get_json_body(request)
            result = StockCategoryService.update(category_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, category_id):
        try:
            cascade = request.GET.get("cascade", "false").lower() == "true"
            result = StockCategoryService.deactivate(category_id, cascade=cascade)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== STOCK ITEMS ====================

class StockItemListView(BaseStockView):
    """GET/POST /api/stock/items/"""
    
    def get(self, request):
        try:
            result = StockItemService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                search=request.GET.get("search"),
                category_id=int(request.GET.get("category_id")) if request.GET.get("category_id") else None,
                item_type=request.GET.get("type"),
                is_purchasable=request.GET.get("purchasable") == "true" if request.GET.get("purchasable") else None,
                is_sellable=request.GET.get("sellable") == "true" if request.GET.get("sellable") else None,
                is_producible=request.GET.get("producible") == "true" if request.GET.get("producible") else None,
                low_stock_only=request.GET.get("low_stock") == "true",
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = StockItemService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class StockItemDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/items/<id>/"""
    
    def get(self, request, item_id):
        try:
            result = StockItemService.get(item_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, item_id):
        try:
            data = self.get_json_body(request)
            result = StockItemService.update(item_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, item_id):
        try:
            force = request.GET.get("force", "false").lower() == "true"
            result = StockItemService.deactivate(item_id, force=force)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockItemSearchView(BaseStockView):
    """GET /api/stock/items/search/"""
    
    def get(self, request):
        try:
            query = request.GET.get("q", "")
            limit = int(request.GET.get("limit", 20))
            result = StockItemService.search(query, limit)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockItemBarcodeView(BaseStockView):
    """GET /api/stock/items/barcode/<barcode>/"""
    
    def get(self, request, barcode):
        try:
            result = StockItemService.find_by_barcode(barcode)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockItemStatsView(BaseStockView):
    """GET /api/stock/items/stats/"""
    
    def get(self, request):
        try:
            result = StockItemService.get_stats()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== STOCK LEVELS ====================

class StockLevelListView(BaseStockView):
    """GET /api/stock/levels/"""
    
    def get(self, request):
        try:
            result = StockLevelService.get_all(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 50)),
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
                category_id=int(request.GET.get("category_id")) if request.GET.get("category_id") else None,
                low_stock_only=request.GET.get("low_stock") == "true",
                search=request.GET.get("search"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockLevelItemView(BaseStockView):
    """GET /api/stock/levels/item/<id>/"""
    
    def get(self, request, item_id):
        try:
            result = StockLevelService.get_for_item(item_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockLevelLocationView(BaseStockView):
    """GET /api/stock/levels/location/<id>/"""
    
    def get(self, request, location_id):
        try:
            result = StockLevelService.get_for_location(location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockAdjustView(BaseStockView):
    """POST /api/stock/adjust/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockLevelService.adjust(
                stock_item_id=data["stock_item_id"],
                location_id=data["location_id"],
                quantity=data["quantity"],
                movement_type=data["movement_type"],
                user_id=user_id or data.get("user_id"),
                unit_id=data.get("unit_id"),
                batch_id=data.get("batch_id"),
                unit_cost=data.get("unit_cost"),
                reference_type=data.get("reference_type"),
                reference_id=data.get("reference_id"),
                notes=data.get("notes", ""),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class StockReserveView(BaseStockView):
    """POST /api/stock/reserve/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockLevelService.reserve(
                stock_item_id=data["stock_item_id"],
                location_id=data["location_id"],
                quantity=data["quantity"],
                user_id=user_id or data.get("user_id"),
                reference_type=data.get("reference_type"),
                reference_id=data.get("reference_id"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockReleaseReservationView(BaseStockView):
    """POST /api/stock/release-reservation/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockLevelService.release_reservation(
                stock_item_id=data["stock_item_id"],
                location_id=data["location_id"],
                quantity=data["quantity"],
                user_id=user_id or data.get("user_id"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class LowStockView(BaseStockView):
    """GET /api/stock/low-stock/"""
    
    def get(self, request):
        try:
            location_id = int(request.GET.get("location_id")) if request.GET.get("location_id") else None
            result = StockLevelService.get_low_stock_items(location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== TRANSACTIONS ====================

class TransactionListView(BaseStockView):
    """GET /api/stock/transactions/"""
    
    def get(self, request):
        try:
            from datetime import datetime
            
            date_from = None
            date_to = None
            if request.GET.get("date_from"):
                date_from = datetime.fromisoformat(request.GET["date_from"]).date()
            if request.GET.get("date_to"):
                date_to = datetime.fromisoformat(request.GET["date_to"]).date()
            
            result = StockTransactionService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 50)),
                stock_item_id=int(request.GET.get("item_id")) if request.GET.get("item_id") else None,
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
                movement_type=request.GET.get("type"),
                date_from=date_from,
                date_to=date_to,
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class TransactionHistoryView(BaseStockView):
    """GET /api/stock/transactions/item/<id>/"""
    
    def get(self, request, item_id):
        try:
            days = int(request.GET.get("days", 30))
            result = StockTransactionService.get_item_history(item_id, days)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== BATCHES ====================

class BatchListView(BaseStockView):
    """GET/POST /api/stock/batches/"""
    
    def get(self, request):
        try:
            result = StockBatchService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 50)),
                stock_item_id=int(request.GET.get("item_id")) if request.GET.get("item_id") else None,
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
                status=request.GET.get("status"),
                expiring_within_days=int(request.GET.get("expiring_days")) if request.GET.get("expiring_days") else None,
                expired_only=request.GET.get("expired") == "true",
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            from datetime import datetime
            
            expiry_date = None
            if data.get("expiry_date"):
                expiry_date = datetime.fromisoformat(data["expiry_date"]).date()
            
            result = StockBatchService.create(
                stock_item_id=data["stock_item_id"],
                location_id=data["location_id"],
                quantity=data["quantity"],
                unit_cost=data.get("unit_cost", 0),
                batch_number=data.get("batch_number"),
                expiry_date=expiry_date,
                supplier_id=data.get("supplier_id"),
                purchase_order_id=data.get("purchase_order_id"),
                quality_status=data.get("quality_status", "PASSED"),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class BatchDetailView(BaseStockView):
    """GET/PUT /api/stock/batches/<id>/"""
    
    def get(self, request, batch_id):
        try:
            result = StockBatchService.get(batch_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, batch_id):
        try:
            data = self.get_json_body(request)
            result = StockBatchService.update(batch_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class BatchConsumeView(BaseStockView):
    """POST /api/stock/batches/<id>/consume/"""
    
    def post(self, request, batch_id):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockBatchService.consume(
                batch_id=batch_id,
                quantity=data["quantity"],
                movement_type=data["movement_type"],
                user_id=user_id or data.get("user_id"),
                notes=data.get("notes", ""),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class BatchAutoConsumeView(BaseStockView):
    """POST /api/stock/batches/auto-consume/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockBatchService.auto_consume(
                stock_item_id=data["stock_item_id"],
                location_id=data["location_id"],
                quantity=data["quantity"],
                movement_type=data["movement_type"],
                user_id=user_id or data.get("user_id"),
                # costing_method=data.get("costing_method"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class ExpiringBatchesView(BaseStockView):
    """GET /api/stock/batches/expiring/"""
    
    def get(self, request):
        try:
            days = int(request.GET.get("days", 7))
            result = StockBatchService.get_expiring_batches(days)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class ExpiredBatchesView(BaseStockView):
    """GET /api/stock/batches/expired/"""
    
    def get(self, request):
        try:
            result = StockBatchService.get_expired_batches()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== SUPPLIERS ====================

class SupplierListView(BaseStockView):
    """GET/POST /api/stock/suppliers/"""
    
    def get(self, request):
        try:
            result = SupplierService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                search=request.GET.get("search"),
                active_only=request.GET.get("active", "true").lower() == "true",
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = SupplierService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class SupplierDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/suppliers/<id>/"""
    
    def get(self, request, supplier_id):
        try:
            result = SupplierService.get(supplier_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, supplier_id):
        try:
            data = self.get_json_body(request)
            result = SupplierService.update(supplier_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, supplier_id):
        try:
            result = SupplierService.deactivate(supplier_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class SupplierItemsView(BaseStockView):
    """GET/POST /api/stock/suppliers/<id>/items/"""
    
    def get(self, request, supplier_id):
        try:
            result = SupplierStockItemService.get_for_supplier(supplier_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request, supplier_id):
        try:
            data = self.get_json_body(request)
            result = SupplierStockItemService.add_item(
                supplier_id=supplier_id,
                stock_item_id=data["stock_item_id"],
                unit_id=data["unit_id"],
                price=data["price"],
                **{k: v for k, v in data.items() if k not in ["stock_item_id", "unit_id", "price"]}
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


# ==================== PURCHASE ORDERS ====================

class PurchaseOrderListView(BaseStockView):
    """GET/POST /api/stock/purchase-orders/"""
    
    def get(self, request):
        try:
            from datetime import datetime
            
            date_from = None
            date_to = None
            if request.GET.get("date_from"):
                date_from = datetime.fromisoformat(request.GET["date_from"]).date()
            if request.GET.get("date_to"):
                date_to = datetime.fromisoformat(request.GET["date_to"]).date()
            
            result = PurchaseOrderService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                supplier_id=int(request.GET.get("supplier_id")) if request.GET.get("supplier_id") else None,
                status=request.GET.get("status"),
                payment_status=request.GET.get("payment_status"),
                date_from=date_from,
                date_to=date_to,
                search=request.GET.get("search"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = PurchaseOrderService.create(
                supplier_id=data["supplier_id"],
                delivery_location_id=data["delivery_location_id"],
                created_by_id=user_id or data.get("created_by_id"),
                items=data.get("items", []),
                **{k: v for k, v in data.items() if k not in ["supplier_id", "delivery_location_id", "created_by_id", "items"]}
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class PurchaseOrderDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/purchase-orders/<id>/"""
    
    def get(self, request, po_id):
        try:
            result = PurchaseOrderService.get(po_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, po_id):
        try:
            data = self.get_json_body(request)
            result = PurchaseOrderService.update(po_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class PurchaseOrderActionView(BaseStockView):
    """POST /api/stock/purchase-orders/<id>/<action>/"""
    
    def post(self, request, po_id, action):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            if action == "send":
                result = PurchaseOrderService.send(po_id)
            elif action == "confirm":
                result = PurchaseOrderService.confirm(po_id, approved_by_id=user_id)
            elif action == "cancel":
                result = PurchaseOrderService.cancel(po_id, reason=data.get("reason", ""))
            else:
                return error_response(f"Unknown action: {action}", "invalid_action", 400)
            
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class PurchaseOrderItemView(BaseStockView):
    """POST/PUT/DELETE /api/stock/purchase-orders/<id>/items/"""
    
    def post(self, request, po_id):
        try:
            data = self.get_json_body(request)
            result = PurchaseOrderItemService.add_item(
                purchase_order_id=po_id,
                **data
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class PurchaseOrderItemDetailView(BaseStockView):
    """PUT/DELETE /api/stock/purchase-order-items/<id>/"""
    
    def put(self, request, item_id):
        try:
            data = self.get_json_body(request)
            result = PurchaseOrderItemService.update_item(item_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, item_id):
        try:
            result = PurchaseOrderItemService.remove_item(item_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class PurchaseReceivingView(BaseStockView):
    """POST /api/stock/purchase-orders/<id>/receiving/"""
    
    def post(self, request, po_id):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = PurchaseReceivingService.create(
                purchase_order_id=po_id,
                received_by_id=user_id or data.get("received_by_id"),
                location_id=data.get("location_id"),
                notes=data.get("notes", ""),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class PurchaseReceivingItemView(BaseStockView):
    """POST /api/stock/receiving/<id>/items/"""
    
    def post(self, request, receiving_id):
        try:
            data = self.get_json_body(request)
            from datetime import datetime
            
            expiry_date = None
            if data.get("expiry_date"):
                expiry_date = datetime.fromisoformat(data["expiry_date"]).date()
            
            result = PurchaseReceivingService.add_item(
                receiving_id=receiving_id,
                po_item_id=data["po_item_id"],
                quantity_received=data["quantity_received"],
                batch_number=data.get("batch_number", ""),
                expiry_date=expiry_date,
                unit_cost=data.get("unit_cost"),
                quality_status=data.get("quality_status", "PASSED"),
                notes=data.get("notes", ""),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class PurchaseReceivingCompleteView(BaseStockView):
    """POST /api/stock/receiving/<id>/complete/"""
    
    def post(self, request, receiving_id):
        try:
            result = PurchaseReceivingService.complete(receiving_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== RECIPES ====================

class RecipeListView(BaseStockView):
    """GET/POST /api/stock/recipes/"""
    
    def get(self, request):
        try:
            result = RecipeService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                search=request.GET.get("search"),
                recipe_type=request.GET.get("type"),
                output_item_id=int(request.GET.get("output_item_id")) if request.GET.get("output_item_id") else None,
                active_only=request.GET.get("active", "true").lower() == "true",
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = RecipeService.create(
                created_by_id=user_id or data.get("created_by_id"),
                **{k: v for k, v in data.items() if k != "created_by_id"}
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class RecipeDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/recipes/<id>/"""
    
    def get(self, request, recipe_id):
        try:
            include_cost = request.GET.get("cost", "false").lower() == "true"
            result = RecipeService.get(recipe_id, include_cost=include_cost)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, recipe_id):
        try:
            data = self.get_json_body(request)
            result = RecipeService.update(recipe_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, recipe_id):
        try:
            result = RecipeService.deactivate(recipe_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class RecipeCostView(BaseStockView):
    """GET /api/stock/recipes/<id>/cost/"""
    
    def get(self, request, recipe_id):
        try:
            batch_size = float(request.GET.get("batch_size", 1))
            result = RecipeService.calculate_cost(recipe_id, batch_size)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class RecipeAvailabilityView(BaseStockView):
    """GET /api/stock/recipes/<id>/availability/"""
    
    def get(self, request, recipe_id):
        try:
            quantity = float(request.GET.get("quantity", 1))
            location_id = int(request.GET.get("location_id")) if request.GET.get("location_id") else None
            result = RecipeService.check_availability(recipe_id, quantity, location_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class RecipeIngredientView(BaseStockView):
    """POST /api/stock/recipes/<id>/ingredients/"""
    
    def post(self, request, recipe_id):
        try:
            data = self.get_json_body(request)
            result = RecipeIngredientService.add_ingredient(
                recipe_id=recipe_id,
                **data
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class RecipeIngredientDetailView(BaseStockView):
    """PUT/DELETE /api/stock/recipe-ingredients/<id>/"""
    
    def put(self, request, ingredient_id):
        try:
            data = self.get_json_body(request)
            result = RecipeIngredientService.update_ingredient(ingredient_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, ingredient_id):
        try:
            result = RecipeIngredientService.remove_ingredient(ingredient_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== PRODUCTION ORDERS ====================

class ProductionOrderListView(BaseStockView):
    """GET/POST /api/stock/production-orders/"""
    
    def get(self, request):
        try:
            result = ProductionOrderService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                status=request.GET.get("status"),
                recipe_id=int(request.GET.get("recipe_id")) if request.GET.get("recipe_id") else None,
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = ProductionOrderService.create(
                recipe_id=data["recipe_id"],
                batch_multiplier=data.get("batch_multiplier", 1),
                source_location_id=data["source_location_id"],
                output_location_id=data["output_location_id"],
                created_by_id=user_id or data.get("created_by_id"),
                **{k: v for k, v in data.items() if k not in [
                    "recipe_id", "batch_multiplier", "source_location_id",
                    "output_location_id", "created_by_id"
                ]}
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class ProductionOrderDetailView(BaseStockView):
    """GET/PUT /api/stock/production-orders/<id>/"""
    
    def get(self, request, order_id):
        try:
            result = ProductionOrderService.get(order_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, order_id):
        try:
            data = self.get_json_body(request)
            result = ProductionOrderService.update(order_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class ProductionOrderActionView(BaseStockView):
    """POST /api/stock/production-orders/<id>/<action>/"""
    
    def post(self, request, order_id, action):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            if action == "plan":
                from datetime import datetime
                planned_start = None
                if data.get("planned_start"):
                    planned_start = datetime.fromisoformat(data["planned_start"])
                result = ProductionOrderService.plan(order_id, planned_start)
            elif action == "start":
                result = ProductionOrderService.start(order_id, user_id)
            elif action == "complete":
                result = ProductionOrderService.complete(
                    order_id,
                    actual_output_qty=data.get("actual_output_qty"),
                    user_id=user_id
                )
            elif action == "cancel":
                result = ProductionOrderService.cancel(order_id, reason=data.get("reason", ""))
            elif action == "hold":
                result = ProductionOrderService.hold(order_id)
            elif action == "resume":
                result = ProductionOrderService.resume(order_id)
            else:
                return error_response(f"Unknown action: {action}", "invalid_action", 400)
            
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== TRANSFERS ====================

class TransferListView(BaseStockView):
    """GET/POST /api/stock/transfers/"""
    
    def get(self, request):
        try:
            result = StockTransferService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                from_location_id=int(request.GET.get("from_location_id")) if request.GET.get("from_location_id") else None,
                to_location_id=int(request.GET.get("to_location_id")) if request.GET.get("to_location_id") else None,
                status=request.GET.get("status"),
                transfer_type=request.GET.get("type"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockTransferService.create(
                from_location_id=data["from_location_id"],
                to_location_id=data["to_location_id"],
                requested_by_id=user_id or data.get("requested_by_id"),
                transfer_type=data.get("transfer_type", "INTERNAL"),
                notes=data.get("notes", ""),
                items=data.get("items", []),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class TransferDetailView(BaseStockView):
    """GET/PUT /api/stock/transfers/<id>/"""
    
    def get(self, request, transfer_id):
        try:
            result = StockTransferService.get(transfer_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, transfer_id):
        try:
            data = self.get_json_body(request)
            result = StockTransferService.update(transfer_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class TransferActionView(BaseStockView):
    """POST /api/stock/transfers/<id>/<action>/"""
    
    def post(self, request, transfer_id, action):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            if action == "request":
                result = StockTransferService.request(transfer_id)
            elif action == "approve":
                result = StockTransferService.approve(transfer_id, user_id)
            elif action == "ship":
                result = StockTransferService.ship(transfer_id, user_id)
            elif action == "receive":
                received_quantities = data.get("received_quantities", {})
                result = StockTransferService.receive(transfer_id, user_id, received_quantities)
            elif action == "cancel":
                result = StockTransferService.cancel(transfer_id, reason=data.get("reason", ""))
            else:
                return error_response(f"Unknown action: {action}", "invalid_action", 400)
            
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class TransferItemView(BaseStockView):
    """POST /api/stock/transfers/<id>/items/"""
    
    def post(self, request, transfer_id):
        try:
            data = self.get_json_body(request)
            result = StockTransferItemService.add_item(
                transfer_id=transfer_id,
                **data
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class QuickTransferView(BaseStockView):
    """POST /api/stock/transfers/quick/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockTransferService.quick_transfer(
                from_location_id=data["from_location_id"],
                to_location_id=data["to_location_id"],
                stock_item_id=data["stock_item_id"],
                quantity=data["quantity"],
                user_id=user_id or data.get("user_id"),
                unit_id=data.get("unit_id"),
                batch_id=data.get("batch_id"),
                notes=data.get("notes", ""),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== STOCK COUNTS ====================

class StockCountListView(BaseStockView):
    """GET/POST /api/stock/counts/"""
    
    def get(self, request):
        try:
            result = StockCountService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 20)),
                location_id=int(request.GET.get("location_id")) if request.GET.get("location_id") else None,
                status=request.GET.get("status"),
                count_type=request.GET.get("type"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = StockCountService.create(
                location_id=data["location_id"],
                count_type=data["count_type"],
                counted_by_id=user_id or data.get("counted_by_id"),
                category_id=data.get("category_id"),
                auto_adjust=data.get("auto_adjust", False),
                notes=data.get("notes", ""),
                include_zero_stock=data.get("include_zero_stock", True),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class StockCountDetailView(BaseStockView):
    """GET /api/stock/counts/<id>/"""
    
    def get(self, request, count_id):
        try:
            result = StockCountService.get(count_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockCountActionView(BaseStockView):
    """POST /api/stock/counts/<id>/<action>/"""
    
    def post(self, request, count_id, action):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            if action == "start":
                result = StockCountService.start(count_id)
            elif action == "complete":
                result = StockCountService.complete(count_id)
            elif action == "approve":
                apply_adjustments = data.get("apply_adjustments", True)
                result = StockCountService.approve(count_id, user_id, apply_adjustments)
            elif action == "cancel":
                result = StockCountService.cancel(count_id, reason=data.get("reason", ""))
            else:
                return error_response(f"Unknown action: {action}", "invalid_action", 400)
            
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class StockCountRecordView(BaseStockView):
    """POST /api/stock/counts/<id>/record/"""
    
    def post(self, request, count_id):
        try:
            data = self.get_json_body(request)
            result = StockCountService.record_count(
                count_id=count_id,
                item_id=data["item_id"],
                counted_quantity=data["counted_quantity"],
                reason_code_id=data.get("reason_code_id"),
                notes=data.get("notes", ""),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class VarianceCodeListView(BaseStockView):
    """GET/POST /api/stock/variance-codes/"""
    
    def get(self, request):
        try:
            active_only = request.GET.get("active", "true").lower() == "true"
            result = VarianceReasonCodeService.list(active_only)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = VarianceReasonCodeService.create(**data)
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class VarianceCodeSeedView(BaseStockView):
    """POST /api/stock/variance-codes/seed/"""
    
    def post(self, request):
        try:
            result = VarianceReasonCodeService.seed_defaults()
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== PRODUCT LINKS ====================

class ProductLinkListView(BaseStockView):
    """GET /api/stock/product-links/"""
    
    def get(self, request):
        try:
            result = ProductStockLinkService.list(
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 50)),
                link_type=request.GET.get("type"),
                active_only=request.GET.get("active", "true").lower() == "true",
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class ProductLinkDetailView(BaseStockView):
    """GET/PUT/DELETE /api/stock/product-links/<id>/"""
    
    def get(self, request, link_id):
        try:
            result = ProductStockLinkService.get(link_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def put(self, request, link_id):
        try:
            data = self.get_json_body(request)
            result = ProductStockLinkService.update(link_id, **data)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
    
    def delete(self, request, link_id):
        try:
            link = ProductStockLinkService.get_by_id(link_id)
            if link:
                result = ProductStockLinkService.unlink(link.product_id)
                return self.success(result)
            raise NotFoundError("Product link", link_id)
        except Exception as e:
            return handle_service_error(e)


class ProductLinkByProductView(BaseStockView):
    """GET /api/stock/products/<id>/link/"""
    
    def get(self, request, product_id):
        try:
            result = ProductStockLinkService.get_by_product(product_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class ProductLinkToRecipeView(BaseStockView):
    """POST /api/stock/products/<id>/link-recipe/"""
    
    def post(self, request, product_id):
        try:
            data = self.get_json_body(request)
            result = ProductStockLinkService.link_to_recipe(
                product_id=product_id,
                recipe_id=data["recipe_id"],
                deduct_on_status=data.get("deduct_on_status", "PREPARING"),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class ProductLinkToItemView(BaseStockView):
    """POST /api/stock/products/<id>/link-item/"""
    
    def post(self, request, product_id):
        try:
            data = self.get_json_body(request)
            result = ProductStockLinkService.link_to_item(
                product_id=product_id,
                stock_item_id=data["stock_item_id"],
                quantity_per_sale=data.get("quantity_per_sale", 1),
                unit_id=data.get("unit_id"),
                deduct_on_status=data.get("deduct_on_status", "PREPARING"),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class ProductLinkWithComponentsView(BaseStockView):
    """POST /api/stock/products/<id>/link-components/"""
    
    def post(self, request, product_id):
        try:
            data = self.get_json_body(request)
            result = ProductStockLinkService.link_with_components(
                product_id=product_id,
                components=data["components"],
                deduct_on_status=data.get("deduct_on_status", "PREPARING"),
            )
            return self.success(result, 201)
        except Exception as e:
            return handle_service_error(e)


class ProductUnlinkView(BaseStockView):
    """DELETE /api/stock/products/<id>/unlink/"""
    
    def delete(self, request, product_id):
        try:
            result = ProductStockLinkService.unlink(product_id)
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


# ==================== ORDER INTEGRATION ====================

class OrderStockDeductView(BaseStockView):
    """POST /api/stock/orders/deduct/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = OrderStockService.deduct_for_order(
                order_id=data["order_id"],
                order_items=data["order_items"],
                location_id=data["location_id"],
                user_id=user_id or data.get("user_id"),
                order_status=data.get("order_status"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class OrderStockReverseView(BaseStockView):
    """POST /api/stock/orders/reverse/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = OrderStockService.reverse_deduction(
                order_id=data["order_id"],
                user_id=user_id or data.get("user_id"),
                reason=data.get("reason", "Order cancelled"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class OrderStockAvailabilityView(BaseStockView):
    """POST /api/stock/orders/check-availability/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            result = OrderStockService.check_availability(
                order_items=data["order_items"],
                location_id=data["location_id"],
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)


class OrderStockReserveView(BaseStockView):
    """POST /api/stock/orders/reserve/"""
    
    def post(self, request):
        try:
            data = self.get_json_body(request)
            user_id = self.get_user_id(request)
            
            result = OrderStockService.reserve_for_order(
                order_id=data["order_id"],
                order_items=data["order_items"],
                location_id=data["location_id"],
                user_id=user_id or data.get("user_id"),
            )
            return self.success(result)
        except Exception as e:
            return handle_service_error(e)
