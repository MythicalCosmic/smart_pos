"""
Stock Services - Complete stock management business logic

Usage:
    from stock.services import StockItemService, StockLevelService
    
    # Create item
    result = StockItemService.create(name="Flour", base_unit_id=1, ...)
    
    # Adjust stock
    StockLevelService.adjust(stock_item_id=1, location_id=1, quantity=100, ...)
"""

# Base utilities
from stock.services.base_service import (
    ServiceError,
    ValidationError,
    NotFoundError,
    BusinessRuleError,
    InsufficientStockError,
    success_response,
    error_response,
    paginate_queryset,
    to_decimal,
    round_decimal,
    generate_number,
    get_date_range,
    BaseService,
)
# Settings
from .settings_service import (
    StockSettingsService,
    AlertConfigService,
)

# Core entities
from .location_service import StockLocationService
from .unit_service import StockUnitService, StockItemUnitService
from .category_service import StockCategoryService
from .item_service import StockItemService

# Stock operations
from .level_service import StockLevelService, StockTransactionService
from .batch_service import StockBatchService

# Suppliers & Purchasing
from .supplier_service import SupplierService, SupplierStockItemService
from .purchase_service import (
    PurchaseOrderService,
    PurchaseOrderItemService,
    PurchaseReceivingService,
)

# Recipes & Production
from .recipe_service import (
    RecipeService,
    RecipeIngredientService,
    RecipeStepService,
)
from .production_service import (
    ProductionOrderService,
    ProductionOrderIngredientService,
    ProductionOrderOutputService,
)

# Transfers & Counts
from .transfer_service import StockTransferService, StockTransferItemService
from .count_service import (
    StockCountService,
    StockCountItemService,
    VarianceReasonCodeService,
)

# Product Links & Order Integration
from .product_link_service import ProductStockLinkService, ProductComponentService
from .order_service import OrderStockService, OrderStatusHandler


__all__ = [
    # Base
    "ServiceError",
    "ValidationError", 
    "NotFoundError",
    "BusinessRuleError",
    "InsufficientStockError",
    "success_response",
    "error_response",
    "paginate_queryset",
    "to_decimal",
    "round_decimal",
    "generate_number",
    "get_date_range",
    "BaseService",
    
    # Settings
    "StockSettingsService",
    "AlertConfigService",
    
    # Core
    "StockLocationService",
    "StockUnitService",
    "StockItemUnitService",
    "StockCategoryService",
    "StockItemService",
    
    # Stock operations
    "StockLevelService",
    "StockTransactionService",
    "StockBatchService",
    
    # Suppliers & Purchasing
    "SupplierService",
    "SupplierStockItemService",
    "PurchaseOrderService",
    "PurchaseOrderItemService",
    "PurchaseReceivingService",
    
    # Recipes & Production
    "RecipeService",
    "RecipeIngredientService",
    "RecipeStepService",
    "ProductionOrderService",
    "ProductionOrderIngredientService",
    "ProductionOrderOutputService",
    
    # Transfers & Counts
    "StockTransferService",
    "StockTransferItemService",
    "StockCountService",
    "StockCountItemService",
    "VarianceReasonCodeService",
    
    # Product Links & Order
    "ProductStockLinkService",
    "ProductComponentService",
    "OrderStockService",
    "OrderStatusHandler",
]
