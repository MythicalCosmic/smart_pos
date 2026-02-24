from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path("settings/", views.StockSettingsView.as_view(), name="settings"),
    path("settings/toggle/", views.StockSettingsToggleView.as_view(), name="settings-toggle"),
    path("alerts/", views.AlertConfigListView.as_view(), name="alerts"),
    
    path("locations/", views.LocationListView.as_view(), name="location-list"),
    path("locations/<int:location_id>/", views.LocationDetailView.as_view(), name="location-detail"),
    path("locations/<int:location_id>/set-default/", views.LocationSetDefaultView.as_view(), name="location-set-default"),
    
    path("units/", views.UnitListView.as_view(), name="unit-list"),
    path("units/<int:unit_id>/", views.UnitDetailView.as_view(), name="unit-detail"),
    path("units/convert/", views.UnitConvertView.as_view(), name="unit-convert"),
    
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/<int:category_id>/", views.CategoryDetailView.as_view(), name="category-detail"),
    
    path("items/", views.StockItemListView.as_view(), name="item-list"),
    path("items/search/", views.StockItemSearchView.as_view(), name="item-search"),
    path("items/stats/", views.StockItemStatsView.as_view(), name="item-stats"),
    path("items/barcode/<str:barcode>/", views.StockItemBarcodeView.as_view(), name="item-barcode"),
    path("items/<int:item_id>/", views.StockItemDetailView.as_view(), name="item-detail"),
    
    path("levels/", views.StockLevelListView.as_view(), name="level-list"),
    path("levels/item/<int:item_id>/", views.StockLevelItemView.as_view(), name="level-item"),
    path("levels/location/<int:location_id>/", views.StockLevelLocationView.as_view(), name="level-location"),
    path("low-stock/", views.LowStockView.as_view(), name="low-stock"),
    
    path("adjust/", views.StockAdjustView.as_view(), name="adjust"),
    path("reserve/", views.StockReserveView.as_view(), name="reserve"),
    path("release-reservation/", views.StockReleaseReservationView.as_view(), name="release-reservation"),
    
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    path("transactions/item/<int:item_id>/", views.TransactionHistoryView.as_view(), name="transaction-history"),
    
    path("batches/", views.BatchListView.as_view(), name="batch-list"),
    path("batches/expiring/", views.ExpiringBatchesView.as_view(), name="batch-expiring"),
    path("batches/expired/", views.ExpiredBatchesView.as_view(), name="batch-expired"),
    path("batches/auto-consume/", views.BatchAutoConsumeView.as_view(), name="batch-auto-consume"),
    path("batches/<int:batch_id>/", views.BatchDetailView.as_view(), name="batch-detail"),
    path("batches/<int:batch_id>/consume/", views.BatchConsumeView.as_view(), name="batch-consume"),
    
    path("suppliers/", views.SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:supplier_id>/", views.SupplierDetailView.as_view(), name="supplier-detail"),
    path("suppliers/<int:supplier_id>/items/", views.SupplierItemsView.as_view(), name="supplier-items"),
    
    path("purchase-orders/", views.PurchaseOrderListView.as_view(), name="po-list"),
    path("purchase-orders/<int:po_id>/", views.PurchaseOrderDetailView.as_view(), name="po-detail"),
    path("purchase-orders/<int:po_id>/items/", views.PurchaseOrderItemView.as_view(), name="po-items"),
    path("purchase-orders/<int:po_id>/<str:action>/", views.PurchaseOrderActionView.as_view(), name="po-action"),
    path("purchase-order/<int:po_id>/receiving/", views.PurchaseReceivingView.as_view(), name="po-receiving"),
    path("purchase-order-items/<int:item_id>/", views.PurchaseOrderItemDetailView.as_view(), name="po-item-detail"),
    path("receiving/<int:receiving_id>/items/", views.PurchaseReceivingItemView.as_view(), name="receiving-items"),
    path("receiving/<int:receiving_id>/complete/", views.PurchaseReceivingCompleteView.as_view(), name="receiving-complete"),
    
    path("recipes/", views.RecipeListView.as_view(), name="recipe-list"),
    path("recipes/<int:recipe_id>/", views.RecipeDetailView.as_view(), name="recipe-detail"),
    path("recipes/<int:recipe_id>/cost/", views.RecipeCostView.as_view(), name="recipe-cost"),
    path("recipes/<int:recipe_id>/availability/", views.RecipeAvailabilityView.as_view(), name="recipe-availability"),
    path("recipes/<int:recipe_id>/ingredients/", views.RecipeIngredientView.as_view(), name="recipe-ingredients"),
    path("recipe-ingredients/<int:ingredient_id>/", views.RecipeIngredientDetailView.as_view(), name="recipe-ingredient-detail"),
    
    path("production-orders/", views.ProductionOrderListView.as_view(), name="production-list"),
    path("production-orders/<int:order_id>/", views.ProductionOrderDetailView.as_view(), name="production-detail"),
    path("production-orders/<int:order_id>/<str:action>/", views.ProductionOrderActionView.as_view(), name="production-action"),
    
    path("transfers/", views.TransferListView.as_view(), name="transfer-list"),
    path("transfers/quick/", views.QuickTransferView.as_view(), name="transfer-quick"),
    path("transfers/<int:transfer_id>/", views.TransferDetailView.as_view(), name="transfer-detail"),
    path("transfers/<int:transfer_id>/items/", views.TransferItemView.as_view(), name="transfer-items"),
    path("transfers/<int:transfer_id>/<str:action>/", views.TransferActionView.as_view(), name="transfer-action"),
    
    path("counts/", views.StockCountListView.as_view(), name="count-list"),
    path("counts/<int:count_id>/", views.StockCountDetailView.as_view(), name="count-detail"),
    path("counts/<int:count_id>/record/", views.StockCountRecordView.as_view(), name="count-record"),
    path("counts/<int:count_id>/<str:action>/", views.StockCountActionView.as_view(), name="count-action"),
    path("variance-codes/", views.VarianceCodeListView.as_view(), name="variance-codes"),
    path("variance-codes/seed/", views.VarianceCodeSeedView.as_view(), name="variance-codes-seed"),
    path("product-links/", views.ProductLinkListView.as_view(), name="product-link-list"),
    path("product-links/<int:link_id>/", views.ProductLinkDetailView.as_view(), name="product-link-detail"),
    path("products/<int:product_id>/link/", views.ProductLinkByProductView.as_view(), name="product-link-get"),
    path("products/<int:product_id>/link-recipe/", views.ProductLinkToRecipeView.as_view(), name="product-link-recipe"),
    path("products/<int:product_id>/link-item/", views.ProductLinkToItemView.as_view(), name="product-link-item"),
    path("products/<int:product_id>/link-components/", views.ProductLinkWithComponentsView.as_view(), name="product-link-components"),
    path("products/<int:product_id>/unlink/", views.ProductUnlinkView.as_view(), name="product-unlink"),
    
    path("orders/deduct/", views.OrderStockDeductView.as_view(), name="order-deduct"),
    path("orders/reverse/", views.OrderStockReverseView.as_view(), name="order-reverse"),
    path("orders/check-availability/", views.OrderStockAvailabilityView.as_view(), name="order-check-availability"),
    path("orders/reserve/", views.OrderStockReserveView.as_view(), name="order-reserve"),
]
