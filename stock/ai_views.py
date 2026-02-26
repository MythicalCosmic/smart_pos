from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from .services.ai_assistant_service import AIStockAssistant


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantQueryView(View):
    """
    POST /api/stock/ai/query/
    
    Main endpoint for natural language queries.
    
    Request:
    {
        "query": "How much flour do we have?",
        "context": {...},  // Optional: previous conversation context
        "location_id": 1   // Optional: filter by location
    }
    
    Response:
    {
        "success": true,
        "intent": "stock_level",
        "response": "📦 Flour stock: 5000g at Main Warehouse...",
        "data": {...},
        "suggestions": ["Show low stock", "Check expiring"],
        "context": {...}
    }
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "error": "Invalid JSON"
            }, status=400)
        
        query = data.get("query", "").strip()
        
        if not query:
            return JsonResponse({
                "success": False,
                "error": "Query is required"
            }, status=400)
        
        # Get optional parameters
        context = data.get("context")
        location_id = data.get("location_id")
        user_id = request.user.id if request.user.is_authenticated else None
        
        # Process query
        result = AIStockAssistant.process_query(
            query=query,
            context=context,
            user_id=user_id,
            location_id=location_id
        )
        
        return JsonResponse(result)


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantSuggestionsView(View):
    """
    GET /api/stock/ai/suggestions/
    
    Get suggested queries based on current stock state.
    """
    
    def get(self, request):
        from django.db.models import F, Sum
        from django.utils import timezone
        from datetime import timedelta
        from stock.models import StockLevel, StockBatch, PurchaseOrder
        
        suggestions = []
        
        # Check low stock
        low_stock_count = StockLevel.objects.filter(
            quantity__lte=F("stock_item__reorder_point")
        ).count()
        
        if low_stock_count > 0:
            suggestions.append({
                "query": "Show low stock items",
                "reason": f"{low_stock_count} items below reorder level",
                "priority": "high"
            })
        
        # Check expiring
        expiring_count = StockBatch.objects.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=7),
            expiry_date__gt=timezone.now().date(),
            current_quantity__gt=0
        ).count()
        
        if expiring_count > 0:
            suggestions.append({
                "query": "What's expiring this week?",
                "reason": f"{expiring_count} batches expiring soon",
                "priority": "high"
            })
        
        # Check pending orders
        pending_count = PurchaseOrder.objects.filter(
            status__in=["SENT", "CONFIRMED", "PARTIAL"]
        ).count()
        
        if pending_count > 0:
            suggestions.append({
                "query": "Show pending deliveries",
                "reason": f"{pending_count} orders waiting",
                "priority": "medium"
            })
        
        # Default suggestions
        suggestions.extend([
            {"query": "Stock overview", "reason": "See inventory summary", "priority": "low"},
            {"query": "Top 10 most used items this month", "reason": "Analyze consumption", "priority": "low"},
            {"query": "Stock value by location", "reason": "Financial overview", "priority": "low"},
        ])
        
        return JsonResponse({
            "success": True,
            "suggestions": suggestions[:6]  # Max 6 suggestions
        })


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantQuickActionsView(View):
    """
    GET /api/stock/ai/quick-actions/
    
    Get quick action buttons for common operations.
    """
    
    def get(self, request):
        actions = [
            {
                "id": "low_stock",
                "label": "Low Stock",
                "icon": "warning",
                "query": "Show low stock items"
            },
            {
                "id": "expiring",
                "label": "Expiring",
                "icon": "clock",
                "query": "What's expiring in 7 days?"
            },
            {
                "id": "overview",
                "label": "Overview",
                "icon": "chart",
                "query": "Stock summary"
            },
            {
                "id": "top_items",
                "label": "Top Items",
                "icon": "fire",
                "query": "Top 10 most used items"
            },
            {
                "id": "pending",
                "label": "Pending POs",
                "icon": "truck",
                "query": "Show pending orders"
            },
            {
                "id": "forecast",
                "label": "Forecast",
                "icon": "crystal-ball",
                "query": "When will items run out?"
            },
        ]
        
        return JsonResponse({
            "success": True,
            "actions": actions
        })


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantHistoryView(View):
    """
    GET /api/stock/ai/history/
    POST /api/stock/ai/history/
    
    Manage conversation history (for frontend to persist).
    """
    
    def get(self, request):
        # In a real implementation, this would fetch from database
        # For now, return empty - frontend handles persistence
        return JsonResponse({
            "success": True,
            "history": [],
            "message": "History is managed client-side"
        })
    
    def post(self, request):
        # Could be used to save important queries/responses
        return JsonResponse({
            "success": True,
            "message": "History saved client-side"
        })


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantFeedbackView(View):
    """
    POST /api/stock/ai/feedback/
    
    Submit feedback on AI response quality.
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        
        query = data.get("query")
        response_id = data.get("response_id")
        rating = data.get("rating")  # 1-5 or thumbs_up/thumbs_down
        comment = data.get("comment", "")
        
        # In production, save to database for model improvement
        # For now, just acknowledge
        
        return JsonResponse({
            "success": True,
            "message": "Thank you for your feedback!"
        })



