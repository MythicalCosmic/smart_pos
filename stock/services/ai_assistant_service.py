from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.db.models import Sum, Avg, Count, F, Q, Min, Max
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils import timezone
import re
import json

from stock.models import (
    StockItem, StockLevel, StockTransaction, StockBatch,
    StockLocation, StockCategory, StockUnit,
    Supplier, SupplierStockItem,
    PurchaseOrder, PurchaseOrderItem,
    Recipe, ProductionOrder,
    StockTransfer, StockCount,
    StockSettings
)


class QueryIntent:
    """Detected intent from user query"""
    # Stock levels
    STOCK_LEVEL = "stock_level"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    STOCK_VALUE = "stock_value"
    
    # Movements
    TRANSACTIONS = "transactions"
    MOVEMENT_SUMMARY = "movement_summary"
    
    # Batches
    EXPIRING_BATCHES = "expiring_batches"
    EXPIRED_BATCHES = "expired_batches"
    BATCH_INFO = "batch_info"
    
    # Analytics
    TOP_ITEMS = "top_items"
    CONSUMPTION_RATE = "consumption_rate"
    TREND = "trend"
    COMPARISON = "comparison"
    FORECAST = "forecast"
    
    # Suppliers
    SUPPLIER_INFO = "supplier_info"
    BEST_SUPPLIER = "best_supplier"
    SUPPLIER_PERFORMANCE = "supplier_performance"
    
    # Purchasing
    PURCHASE_ORDERS = "purchase_orders"
    PENDING_ORDERS = "pending_orders"
    
    # Production
    PRODUCTION_INFO = "production_info"
    RECIPE_COST = "recipe_cost"
    
    # General
    SEARCH = "search"
    HELP = "help"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class AIStockAssistant:
    """
    AI-powered stock assistant that processes natural language queries
    and returns conversational responses with stock data.
    """
    
    # ==================== QUERY PATTERNS ====================
    
    INTENT_PATTERNS = {
        # Stock levels
        QueryIntent.STOCK_LEVEL: [
            r"(how much|quantity|stock|level|amount).*(do we have|in stock|available|left)",
            r"(what|show|get).*(stock|inventory|level)",
            r"(stock|level|quantity)\s+(of|for)\s+",
            r"сколько.*есть",  # Russian: how much do we have
            r"qancha.*bor",    # Uzbek: how much is there
        ],
        QueryIntent.LOW_STOCK: [
            r"(low|running low|almost out|need.*(order|restock)|below)",
            r"(what|which|show).*(low|reorder|need.*order)",
            r"kam.*qolgan",    # Uzbek: running low
        ],
        QueryIntent.OUT_OF_STOCK: [
            r"(out of stock|no stock|zero|finished|empty)",
            r"(what|which).*(out|finished|empty|zero)",
        ],
        QueryIntent.STOCK_VALUE: [
            r"(total|overall)?\s*(value|worth|cost).*(stock|inventory)",
            r"(how much|what).*(worth|value)",
            r"inventory.*value",
        ],
        
        # Movements
        QueryIntent.TRANSACTIONS: [
            r"(show|get|list).*(transaction|movement|history)",
            r"(what|which).*(moved|sold|purchased|used|consumed)",
            r"(movement|transaction).*history",
        ],
        QueryIntent.MOVEMENT_SUMMARY: [
            r"(summary|overview).*(movement|transaction|activity)",
            r"(what|how much).*(in|out|moved).*today|week|month",
        ],
        
        # Batches
        QueryIntent.EXPIRING_BATCHES: [
            r"(expir|expire|expiring|about to expire)",
            r"(what|which|show).*(expir|expire|shelf life)",
            r"muddat.*tugay",  # Uzbek: expiring
        ],
        QueryIntent.EXPIRED_BATCHES: [
            r"(already|have)\s*expired",
            r"(expired|past.*date|spoiled)",
        ],
        
        # Analytics
        QueryIntent.TOP_ITEMS: [
            r"(top|most|best|highest|popular)",
            r"(what|which).*(selling|used|consumed|moving|popular)",
            r"(best|top)\s*\d+",
        ],
        QueryIntent.CONSUMPTION_RATE: [
            r"(consumption|usage|burn)\s*(rate|speed)",
            r"(how (fast|quickly)|rate).*(using|consuming|selling)",
            r"(daily|weekly|monthly).*(usage|consumption)",
        ],
        QueryIntent.TREND: [
            r"(trend|trending|pattern|over time)",
            r"(how|what).*(chang|trend|pattern|going)",
            r"(increase|decrease|growth|decline)",
        ],
        QueryIntent.COMPARISON: [
            r"(compare|comparison|versus|vs\.?|difference)",
            r"(which|what).*(better|more|less|higher|lower)",
            r"(\w+)\s+vs\.?\s+(\w+)",
        ],
        QueryIntent.FORECAST: [
            r"(forecast|predict|projection|estimate|when.*run out)",
            r"(how long|when).*(last|run out|need.*order)",
        ],
        
        # Suppliers
        QueryIntent.SUPPLIER_INFO: [
            r"(supplier|vendor).*(info|detail|list|show)",
            r"(who|which).*(supplier|vendor|supply)",
        ],
        QueryIntent.BEST_SUPPLIER: [
            r"(best|cheapest|fastest|recommended).*(supplier|vendor)",
            r"(who|which).*best.*(price|deal|supplier)",
        ],
        
        # Purchasing
        QueryIntent.PURCHASE_ORDERS: [
            r"(purchase|PO|order).*(list|show|status|history)",
            r"(what|which|show).*(purchase|order|PO)",
        ],
        QueryIntent.PENDING_ORDERS: [
            r"(pending|waiting|expected|incoming).*(order|delivery|shipment)",
            r"(what|when).*(arriving|coming|expecting)",
        ],
        
        # Production
        QueryIntent.PRODUCTION_INFO: [
            r"(production|manufacturing).*(info|status|order)",
            r"(what|which).*(producing|production)",
        ],
        QueryIntent.RECIPE_COST: [
            r"(recipe|product).*(cost|price|margin)",
            r"(how much|what).*(cost|make|produce)",
        ],
        
        # General
        QueryIntent.SEARCH: [
            r"(find|search|look for|where is)",
        ],
        QueryIntent.HELP: [
            r"(help|what can you|how do i|commands|capabilities)",
            r"(yordam|помощь)",  # Uzbek/Russian: help
        ],
        QueryIntent.SUMMARY: [
            r"(summary|overview|dashboard|status|report)",
            r"(what|how).*overall.*status",
        ],
    }
    
    # Time period patterns
    TIME_PATTERNS = {
        "today": (0, "day"),
        "yesterday": (-1, "day"),
        "this week": (0, "week"),
        "last week": (-1, "week"),
        "this month": (0, "month"),
        "last month": (-1, "month"),
        "this year": (0, "year"),
        "last year": (-1, "year"),
        r"last (\d+) days?": ("days", None),
        r"last (\d+) weeks?": ("weeks", None),
        r"last (\d+) months?": ("months", None),
        r"past (\d+) days?": ("days", None),
    }
    
    # ==================== MAIN QUERY PROCESSOR ====================
    
    @classmethod
    def process_query(cls, 
                      query: str, 
                      context: Dict = None,
                      user_id: int = None,
                      location_id: int = None) -> Dict[str, Any]:
        """
        Process a natural language query and return response.
        
        Args:
            query: Natural language query from user
            context: Optional conversation context for follow-ups
            user_id: Current user ID
            location_id: Optional location filter
            
        Returns:
            {
                "success": True,
                "intent": "detected_intent",
                "response": "Conversational response text",
                "data": {...},  # Structured data
                "suggestions": ["follow-up question 1", ...],
                "context": {...}  # For follow-up queries
            }
        """
        query = query.strip().lower()
        
        # Detect intent
        intent, confidence = cls._detect_intent(query)
        
        # Extract parameters (items, dates, locations, etc.)
        params = cls._extract_parameters(query, context)
        params["location_id"] = location_id or params.get("location_id")
        
        # Route to appropriate handler
        handler = cls._get_handler(intent)
        
        try:
            result = handler(query, params)
            result["intent"] = intent
            result["success"] = True
            result["context"] = {
                "last_intent": intent,
                "last_params": params,
                "timestamp": timezone.now().isoformat()
            }
            return result
        except Exception as e:
            return {
                "success": False,
                "intent": intent,
                "error": str(e),
                "response": f"Sorry, I encountered an error: {str(e)}",
                "suggestions": ["Try rephrasing your question", "Ask for help"]
            }
    
    @classmethod
    def _detect_intent(cls, query: str) -> Tuple[str, float]:
        """Detect the intent of the query"""
        query_lower = query.lower()
        
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return intent, 0.8
        
        return QueryIntent.UNKNOWN, 0.0
    
    @classmethod
    def _extract_parameters(cls, query: str, context: Dict = None) -> Dict:
        """Extract parameters from query"""
        params = {}
        
        # Extract time period
        params["period"] = cls._extract_time_period(query)
        
        # Extract item names/references
        params["items"] = cls._extract_items(query)
        
        # Extract location references
        params["locations"] = cls._extract_locations(query)
        
        # Extract numbers
        numbers = re.findall(r'\b(\d+)\b', query)
        if numbers:
            params["limit"] = int(numbers[0]) if int(numbers[0]) <= 100 else 10
        else:
            params["limit"] = 10
        
        # Extract category references
        params["categories"] = cls._extract_categories(query)
        
        # Extract supplier references
        params["suppliers"] = cls._extract_suppliers(query)
        
        # Use context for follow-ups
        if context:
            if not params["items"] and context.get("last_params", {}).get("items"):
                params["items"] = context["last_params"]["items"]
            if not params["period"] and context.get("last_params", {}).get("period"):
                params["period"] = context["last_params"]["period"]
        
        return params
    
    @classmethod
    def _extract_time_period(cls, query: str) -> Dict:
        """Extract time period from query"""
        now = timezone.now()
        
        # Check static patterns
        static_periods = {
            "today": (now.date(), now.date()),
            "yesterday": (now.date() - timedelta(days=1), now.date() - timedelta(days=1)),
            "this week": (now.date() - timedelta(days=now.weekday()), now.date()),
            "last week": (
                now.date() - timedelta(days=now.weekday() + 7),
                now.date() - timedelta(days=now.weekday() + 1)
            ),
            "this month": (now.date().replace(day=1), now.date()),
            "last month": (
                (now.date().replace(day=1) - timedelta(days=1)).replace(day=1),
                now.date().replace(day=1) - timedelta(days=1)
            ),
        }
        
        for period_text, (start, end) in static_periods.items():
            if period_text in query.lower():
                return {"start": start, "end": end, "text": period_text}
        
        # Check dynamic patterns (last N days/weeks/months)
        match = re.search(r'(last|past)\s+(\d+)\s+(day|week|month)s?', query.lower())
        if match:
            n = int(match.group(2))
            unit = match.group(3)
            
            if unit == "day":
                start = now.date() - timedelta(days=n)
            elif unit == "week":
                start = now.date() - timedelta(weeks=n)
            elif unit == "month":
                start = now.date() - timedelta(days=n * 30)
            else:
                start = now.date() - timedelta(days=30)
            
            return {"start": start, "end": now.date(), "text": f"last {n} {unit}s"}
        
        # Default to last 30 days
        return {"start": now.date() - timedelta(days=30), "end": now.date(), "text": "last 30 days"}
    
    @classmethod
    def _extract_items(cls, query: str) -> List[Dict]:
        """Extract item references from query"""
        items = []
        
        # Try to find items by name patterns
        # Pattern: "for <item>" or "of <item>" or "<item> stock"
        patterns = [
            r'(?:for|of|about)\s+["\']?([a-zA-Z\s]+)["\']?(?:\s+stock|\s+level)?',
            r'["\']([^"\']+)["\']',  # Quoted names
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                # Try to find in database
                item = StockItem.objects.filter(
                    Q(name__icontains=match.strip()) |
                    Q(sku__iexact=match.strip())
                ).first()
                if item:
                    items.append({"id": item.id, "name": item.name})
        
        return items
    
    @classmethod
    def _extract_locations(cls, query: str) -> List[Dict]:
        """Extract location references from query"""
        locations = []
        
        # Common location keywords
        location_keywords = ["warehouse", "kitchen", "bar", "storage", "store"]
        
        for keyword in location_keywords:
            if keyword in query.lower():
                loc = StockLocation.objects.filter(
                    Q(name__icontains=keyword) | Q(type__iexact=keyword)
                ).first()
                if loc:
                    locations.append({"id": loc.id, "name": loc.name})
        
        # Check for "at <location>" pattern
        match = re.search(r'(?:at|in|from)\s+([a-zA-Z\s]+?)(?:\s+location|\s+warehouse)?(?:\s|$)', query, re.IGNORECASE)
        if match:
            loc_name = match.group(1).strip()
            loc = StockLocation.objects.filter(name__icontains=loc_name).first()
            if loc:
                locations.append({"id": loc.id, "name": loc.name})
        
        return locations
    
    @classmethod
    def _extract_categories(cls, query: str) -> List[Dict]:
        """Extract category references from query"""
        categories = []
        
        # Common category types
        category_keywords = ["raw material", "finished", "packaging", "ingredient", "consumable"]
        
        for keyword in category_keywords:
            if keyword in query.lower():
                cat = StockCategory.objects.filter(
                    Q(name__icontains=keyword) | Q(type__icontains=keyword.replace(" ", "_").upper())
                ).first()
                if cat:
                    categories.append({"id": cat.id, "name": cat.name})
        
        return categories
    
    @classmethod
    def _extract_suppliers(cls, query: str) -> List[Dict]:
        """Extract supplier references from query"""
        suppliers = []
        
        match = re.search(r'(?:from|supplier|vendor)\s+([a-zA-Z\s]+?)(?:\s|$)', query, re.IGNORECASE)
        if match:
            supplier_name = match.group(1).strip()
            supplier = Supplier.objects.filter(name__icontains=supplier_name).first()
            if supplier:
                suppliers.append({"id": supplier.id, "name": supplier.name})
        
        return suppliers
    
    @classmethod
    def _get_handler(cls, intent: str):
        """Get the handler function for an intent"""
        handlers = {
            QueryIntent.STOCK_LEVEL: cls._handle_stock_level,
            QueryIntent.LOW_STOCK: cls._handle_low_stock,
            QueryIntent.OUT_OF_STOCK: cls._handle_out_of_stock,
            QueryIntent.STOCK_VALUE: cls._handle_stock_value,
            QueryIntent.TRANSACTIONS: cls._handle_transactions,
            QueryIntent.MOVEMENT_SUMMARY: cls._handle_movement_summary,
            QueryIntent.EXPIRING_BATCHES: cls._handle_expiring_batches,
            QueryIntent.EXPIRED_BATCHES: cls._handle_expired_batches,
            QueryIntent.TOP_ITEMS: cls._handle_top_items,
            QueryIntent.CONSUMPTION_RATE: cls._handle_consumption_rate,
            QueryIntent.TREND: cls._handle_trend,
            QueryIntent.COMPARISON: cls._handle_comparison,
            QueryIntent.FORECAST: cls._handle_forecast,
            QueryIntent.SUPPLIER_INFO: cls._handle_supplier_info,
            QueryIntent.BEST_SUPPLIER: cls._handle_best_supplier,
            QueryIntent.PURCHASE_ORDERS: cls._handle_purchase_orders,
            QueryIntent.PENDING_ORDERS: cls._handle_pending_orders,
            QueryIntent.PRODUCTION_INFO: cls._handle_production_info,
            QueryIntent.RECIPE_COST: cls._handle_recipe_cost,
            QueryIntent.SEARCH: cls._handle_search,
            QueryIntent.HELP: cls._handle_help,
            QueryIntent.SUMMARY: cls._handle_summary,
            QueryIntent.UNKNOWN: cls._handle_unknown,
        }
        return handlers.get(intent, cls._handle_unknown)
    
    # ==================== INTENT HANDLERS ====================
    
    @classmethod
    def _handle_stock_level(cls, query: str, params: Dict) -> Dict:
        """Handle stock level queries"""
        items = params.get("items", [])
        location_id = params.get("location_id")
        
        if items:
            # Specific item(s)
            item_ids = [i["id"] for i in items]
            levels = StockLevel.objects.filter(
                stock_item_id__in=item_ids
            ).select_related("stock_item", "location")
            
            if location_id:
                levels = levels.filter(location_id=location_id)
            
            data = []
            for level in levels:
                data.append({
                    "item_id": level.stock_item_id,
                    "item_name": level.stock_item.name,
                    "location": level.location.name,
                    "quantity": float(level.quantity),
                    "reserved": float(level.reserved_quantity),
                    "available": float(level.quantity - level.reserved_quantity),
                    "unit": level.stock_item.base_unit.short_name,
                    "min_level": float(level.stock_item.min_stock_level),
                    "is_low": level.quantity <= level.stock_item.reorder_point,
                })
            
            if len(items) == 1:
                item = items[0]
                total_qty = sum(d["quantity"] for d in data)
                response = f"📦 **{item['name']}** stock:\n"
                for d in data:
                    status = "🔴 LOW" if d["is_low"] else "🟢"
                    response += f"  • {d['location']}: {d['quantity']:,.2f} {d['unit']} {status}\n"
                response += f"\n**Total across all locations:** {total_qty:,.2f} {data[0]['unit'] if data else ''}"
            else:
                response = "📦 **Stock Levels:**\n"
                for d in data:
                    status = "🔴" if d["is_low"] else "🟢"
                    response += f"{status} {d['item_name']}: {d['quantity']:,.2f} {d['unit']} @ {d['location']}\n"
        else:
            # General stock overview
            queryset = StockLevel.objects.select_related("stock_item", "location")
            if location_id:
                queryset = queryset.filter(location_id=location_id)
            
            total_items = queryset.values("stock_item").distinct().count()
            total_value = sum(
                float(l.quantity * l.stock_item.avg_cost_price) 
                for l in queryset
            )
            
            data = {
                "total_items": total_items,
                "total_value": total_value,
                "locations": list(queryset.values("location__name").annotate(
                    item_count=Count("stock_item", distinct=True),
                    total_qty=Sum("quantity")
                ))
            }
            
            response = f"📊 **Stock Overview:**\n"
            response += f"• Total items tracked: {total_items}\n"
            response += f"• Total inventory value: {total_value:,.0f} UZS\n\n"
            response += "**By Location:**\n"
            for loc in data["locations"]:
                response += f"  • {loc['location__name']}: {loc['item_count']} items\n"
        
        return {
            "response": response,
            "data": data if items else data,
            "suggestions": [
                "Show low stock items",
                "What's the stock value?",
                "Show expiring batches"
            ]
        }
    
    @classmethod
    def _handle_low_stock(cls, query: str, params: Dict) -> Dict:
        """Handle low stock queries"""
        location_id = params.get("location_id")
        limit = params.get("limit", 20)
        
        queryset = StockLevel.objects.filter(
            quantity__lte=F("stock_item__reorder_point"),
            stock_item__is_active=True
        ).select_related("stock_item", "location")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        queryset = queryset.order_by("quantity")[:limit]
        
        data = []
        for level in queryset:
            data.append({
                "item_id": level.stock_item_id,
                "item_name": level.stock_item.name,
                "sku": level.stock_item.sku,
                "location": level.location.name,
                "quantity": float(level.quantity),
                "reorder_point": float(level.stock_item.reorder_point),
                "min_level": float(level.stock_item.min_stock_level),
                "unit": level.stock_item.base_unit.short_name,
                "shortage": float(level.stock_item.reorder_point - level.quantity),
            })
        
        if data:
            response = f"⚠️ **Low Stock Alert - {len(data)} items need attention:**\n\n"
            for i, item in enumerate(data[:10], 1):
                response += f"{i}. **{item['item_name']}**\n"
                response += f"   Current: {item['quantity']:,.2f} {item['unit']} | Reorder at: {item['reorder_point']:,.2f}\n"
                response += f"   📍 {item['location']}\n"
            
            if len(data) > 10:
                response += f"\n... and {len(data) - 10} more items"
        else:
            response = "✅ **Great news!** All items are above reorder levels. No immediate restocking needed."
        
        return {
            "response": response,
            "data": {"low_stock_items": data, "count": len(data)},
            "suggestions": [
                "Create purchase order for low stock",
                "Show critical items (below minimum)",
                "Which supplier for these items?"
            ]
        }
    
    @classmethod
    def _handle_out_of_stock(cls, query: str, params: Dict) -> Dict:
        """Handle out of stock queries"""
        location_id = params.get("location_id")
        
        queryset = StockLevel.objects.filter(
            quantity__lte=0,
            stock_item__is_active=True
        ).select_related("stock_item", "location")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        data = []
        for level in queryset:
            data.append({
                "item_id": level.stock_item_id,
                "item_name": level.stock_item.name,
                "sku": level.stock_item.sku,
                "location": level.location.name,
                "last_movement": level.last_movement_at.isoformat() if level.last_movement_at else None,
            })
        
        if data:
            response = f"🔴 **Out of Stock - {len(data)} items:**\n\n"
            for item in data[:15]:
                response += f"• **{item['item_name']}** @ {item['location']}\n"
            
            if len(data) > 15:
                response += f"\n... and {len(data) - 15} more"
        else:
            response = "✅ **All items are in stock!** No zero-quantity items found."
        
        return {
            "response": response,
            "data": {"out_of_stock": data, "count": len(data)},
            "suggestions": [
                "Show low stock items",
                "Create purchase order",
                "When were these last restocked?"
            ]
        }
    
    @classmethod
    def _handle_stock_value(cls, query: str, params: Dict) -> Dict:
        """Handle stock value queries"""
        location_id = params.get("location_id")
        
        queryset = StockLevel.objects.filter(
            stock_item__is_active=True,
            quantity__gt=0
        ).select_related("stock_item", "location")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Calculate values
        total_value = Decimal("0")
        by_location = {}
        by_category = {}
        
        for level in queryset:
            value = level.quantity * level.stock_item.avg_cost_price
            total_value += value
            
            # By location
            loc_name = level.location.name
            if loc_name not in by_location:
                by_location[loc_name] = Decimal("0")
            by_location[loc_name] += value
            
            # By category
            cat_name = level.stock_item.category.name if level.stock_item.category else "Uncategorized"
            if cat_name not in by_category:
                by_category[cat_name] = Decimal("0")
            by_category[cat_name] += value
        
        data = {
            "total_value": float(total_value),
            "by_location": {k: float(v) for k, v in by_location.items()},
            "by_category": {k: float(v) for k, v in sorted(by_category.items(), key=lambda x: x[1], reverse=True)},
        }
        
        response = f"💰 **Total Inventory Value: {total_value:,.0f} UZS**\n\n"
        
        response += "**By Location:**\n"
        for loc, val in sorted(by_location.items(), key=lambda x: x[1], reverse=True):
            pct = (val / total_value * 100) if total_value > 0 else 0
            response += f"  • {loc}: {val:,.0f} UZS ({pct:.1f}%)\n"
        
        response += "\n**Top Categories:**\n"
        for cat, val in list(data["by_category"].items())[:5]:
            pct = (val / float(total_value) * 100) if total_value > 0 else 0
            response += f"  • {cat}: {val:,.0f} UZS ({pct:.1f}%)\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Show most valuable items",
                "Compare value this month vs last month",
                "Show slow-moving inventory"
            ]
        }
    
    @classmethod
    def _handle_transactions(cls, query: str, params: Dict) -> Dict:
        """Handle transaction history queries"""
        items = params.get("items", [])
        period = params.get("period", {})
        location_id = params.get("location_id")
        limit = params.get("limit", 20)
        
        queryset = StockTransaction.objects.select_related(
            "stock_item", "location", "user"
        ).order_by("-created_at")
        
        if items:
            queryset = queryset.filter(stock_item_id__in=[i["id"] for i in items])
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if period.get("start"):
            queryset = queryset.filter(created_at__date__gte=period["start"])
        if period.get("end"):
            queryset = queryset.filter(created_at__date__lte=period["end"])
        
        transactions = queryset[:limit]
        
        data = []
        for t in transactions:
            data.append({
                "id": t.id,
                "number": t.transaction_number,
                "item_name": t.stock_item.name,
                "type": t.movement_type,
                "type_display": t.get_movement_type_display(),
                "quantity": float(t.base_quantity),
                "location": t.location.name,
                "date": t.created_at.isoformat(),
                "user": t.user.username if t.user else "System",
            })
        
        response = f"📋 **Recent Transactions ({period.get('text', 'all time')}):**\n\n"
        
        for t in data[:10]:
            emoji = "📥" if t["quantity"] > 0 else "📤"
            response += f"{emoji} {t['date'][:10]} | {t['type_display']}\n"
            response += f"   {t['item_name']}: {t['quantity']:+,.2f} @ {t['location']}\n"
        
        if len(data) > 10:
            response += f"\n... showing 10 of {len(data)} transactions"
        
        return {
            "response": response,
            "data": {"transactions": data, "count": len(data)},
            "suggestions": [
                "Show movement summary",
                "Filter by type (purchases, sales)",
                "Show transactions for specific item"
            ]
        }
    
    @classmethod
    def _handle_movement_summary(cls, query: str, params: Dict) -> Dict:
        """Handle movement summary queries"""
        period = params.get("period", {})
        location_id = params.get("location_id")
        
        queryset = StockTransaction.objects.all()
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if period.get("start"):
            queryset = queryset.filter(created_at__date__gte=period["start"])
        if period.get("end"):
            queryset = queryset.filter(created_at__date__lte=period["end"])
        
        # Group by movement type
        summary = queryset.values("movement_type").annotate(
            count=Count("id"),
            total_qty=Sum("base_quantity")
        )
        
        data = {
            "period": period.get("text", "all time"),
            "movements": {},
            "totals": {"in": 0, "out": 0}
        }
        
        in_types = ["PURCHASE_IN", "TRANSFER_IN", "PRODUCTION_IN", "ADJUSTMENT_PLUS", "RETURN_FROM_CUSTOMER", "OPENING_BALANCE"]
        
        for s in summary:
            data["movements"][s["movement_type"]] = {
                "count": s["count"],
                "quantity": float(s["total_qty"] or 0)
            }
            
            if s["movement_type"] in in_types:
                data["totals"]["in"] += float(s["total_qty"] or 0)
            else:
                data["totals"]["out"] += abs(float(s["total_qty"] or 0))
        
        response = f"📊 **Movement Summary ({period.get('text', 'all time')}):**\n\n"
        response += f"📥 **Total IN:** {data['totals']['in']:,.2f}\n"
        response += f"📤 **Total OUT:** {data['totals']['out']:,.2f}\n"
        response += f"📈 **Net Change:** {data['totals']['in'] - data['totals']['out']:+,.2f}\n\n"
        
        response += "**By Type:**\n"
        for mtype, info in sorted(data["movements"].items(), key=lambda x: abs(x[1]["quantity"]), reverse=True):
            emoji = "📥" if mtype in in_types else "📤"
            response += f"{emoji} {mtype}: {info['count']} transactions, {info['quantity']:,.2f} units\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Show daily breakdown",
                "Compare to last period",
                "Which items moved most?"
            ]
        }
    
    @classmethod
    def _handle_expiring_batches(cls, query: str, params: Dict) -> Dict:
        """Handle expiring batches queries"""
        location_id = params.get("location_id")
        
        # Extract days from query or default to 7
        days_match = re.search(r'(\d+)\s*days?', query)
        days = int(days_match.group(1)) if days_match else 7
        
        expiry_date = timezone.now().date() + timedelta(days=days)
        
        queryset = StockBatch.objects.filter(
            expiry_date__lte=expiry_date,
            expiry_date__gt=timezone.now().date(),
            current_quantity__gt=0,
            status="AVAILABLE"
        ).select_related("stock_item", "location").order_by("expiry_date")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        data = []
        for batch in queryset[:20]:
            days_left = (batch.expiry_date - timezone.now().date()).days
            data.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "item_name": batch.stock_item.name,
                "quantity": float(batch.current_quantity),
                "unit": batch.stock_item.base_unit.short_name,
                "location": batch.location.name,
                "expiry_date": batch.expiry_date.isoformat(),
                "days_left": days_left,
                "value": float(batch.current_quantity * batch.unit_cost),
            })
        
        total_value = sum(d["value"] for d in data)
        
        if data:
            response = f"⏰ **Expiring Soon ({days} days) - {len(data)} batches:**\n\n"
            response += f"💰 Total value at risk: {total_value:,.0f} UZS\n\n"
            
            for batch in data[:10]:
                urgency = "🔴" if batch["days_left"] <= 3 else "🟡"
                response += f"{urgency} **{batch['item_name']}** - {batch['days_left']} days\n"
                response += f"   Batch: {batch['batch_number']} | Qty: {batch['quantity']:,.2f} {batch['unit']}\n"
                response += f"   📍 {batch['location']} | Value: {batch['value']:,.0f} UZS\n\n"
            
            if len(data) > 10:
                response += f"... and {len(data) - 10} more batches"
        else:
            response = f"✅ **No batches expiring in the next {days} days!**"
        
        return {
            "response": response,
            "data": {"expiring_batches": data, "count": len(data), "total_value": total_value},
            "suggestions": [
                "Show expired batches",
                "Mark batch as consumed",
                "Create discount for expiring items"
            ]
        }
    
    @classmethod
    def _handle_expired_batches(cls, query: str, params: Dict) -> Dict:
        """Handle expired batches queries"""
        location_id = params.get("location_id")
        
        queryset = StockBatch.objects.filter(
            expiry_date__lt=timezone.now().date(),
            current_quantity__gt=0
        ).select_related("stock_item", "location").order_by("expiry_date")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        data = []
        for batch in queryset:
            days_expired = (timezone.now().date() - batch.expiry_date).days
            data.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "item_name": batch.stock_item.name,
                "quantity": float(batch.current_quantity),
                "unit": batch.stock_item.base_unit.short_name,
                "location": batch.location.name,
                "expiry_date": batch.expiry_date.isoformat(),
                "days_expired": days_expired,
                "value": float(batch.current_quantity * batch.unit_cost),
            })
        
        total_value = sum(d["value"] for d in data)
        
        if data:
            response = f"🔴 **EXPIRED Batches - {len(data)} batches need attention:**\n\n"
            response += f"💸 Total loss value: {total_value:,.0f} UZS\n\n"
            
            for batch in data[:10]:
                response += f"❌ **{batch['item_name']}**\n"
                response += f"   Expired {batch['days_expired']} days ago | Qty: {batch['quantity']:,.2f} {batch['unit']}\n"
                response += f"   📍 {batch['location']} | Loss: {batch['value']:,.0f} UZS\n\n"
        else:
            response = "✅ **No expired batches!** All stock is within shelf life."
        
        return {
            "response": response,
            "data": {"expired_batches": data, "count": len(data), "total_loss": total_value},
            "suggestions": [
                "Write off expired batches",
                "Show expiring soon",
                "Report on waste this month"
            ]
        }
    
    @classmethod
    def _handle_top_items(cls, query: str, params: Dict) -> Dict:
        """Handle top items queries"""
        period = params.get("period", {})
        location_id = params.get("location_id")
        limit = params.get("limit", 10)
        
        # Determine if top by sales, consumption, value, etc.
        by_sales = any(word in query.lower() for word in ["selling", "sold", "popular", "sales"])
        by_value = any(word in query.lower() for word in ["valuable", "worth", "expensive"])
        
        if by_value:
            # Top by inventory value
            items = StockLevel.objects.filter(
                quantity__gt=0
            ).select_related("stock_item").annotate(
                value=F("quantity") * F("stock_item__avg_cost_price")
            ).order_by("-value")[:limit]
            
            data = [{
                "item_name": i.stock_item.name,
                "quantity": float(i.quantity),
                "value": float(i.value),
                "unit": i.stock_item.base_unit.short_name,
            } for i in items]
            
            response = f"💎 **Top {limit} Most Valuable Items:**\n\n"
            for i, item in enumerate(data, 1):
                response += f"{i}. **{item['item_name']}**\n"
                response += f"   {item['quantity']:,.2f} {item['unit']} = {item['value']:,.0f} UZS\n"
        else:
            # Top by movement/consumption
            queryset = StockTransaction.objects.filter(
                movement_type__in=["SALE_OUT", "PRODUCTION_OUT"]
            )
            
            if period.get("start"):
                queryset = queryset.filter(created_at__date__gte=period["start"])
            if location_id:
                queryset = queryset.filter(location_id=location_id)
            
            top = queryset.values("stock_item__name", "stock_item__base_unit__short_name").annotate(
                total_qty=Sum("base_quantity"),
                transaction_count=Count("id")
            ).order_by("total_qty")[:limit]  # Negative values, so ascending
            
            data = [{
                "item_name": t["stock_item__name"],
                "total_consumed": abs(float(t["total_qty"])),
                "transactions": t["transaction_count"],
                "unit": t["stock_item__base_unit__short_name"],
            } for t in top]
            
            response = f"🔥 **Top {limit} Most Used Items ({period.get('text', 'all time')}):**\n\n"
            for i, item in enumerate(data, 1):
                response += f"{i}. **{item['item_name']}**\n"
                response += f"   {item['total_consumed']:,.2f} {item['unit']} ({item['transactions']} transactions)\n"
        
        return {
            "response": response,
            "data": {"top_items": data},
            "suggestions": [
                "Show consumption trend for top item",
                "Compare this month vs last month",
                "Which items are slow-moving?"
            ]
        }
    
    @classmethod
    def _handle_consumption_rate(cls, query: str, params: Dict) -> Dict:
        """Handle consumption rate queries"""
        items = params.get("items", [])
        period = params.get("period", {})
        location_id = params.get("location_id")
        
        if items:
            item_ids = [i["id"] for i in items]
        else:
            # Get top 10 most consumed
            item_ids = list(StockTransaction.objects.filter(
                movement_type__in=["SALE_OUT", "PRODUCTION_OUT"]
            ).values_list("stock_item_id", flat=True).annotate(
                total=Sum("base_quantity")
            ).order_by("total")[:10])
        
        data = []
        for item_id in item_ids:
            item = StockItem.objects.get(id=item_id)
            
            # Calculate daily consumption over period
            start_date = period.get("start", timezone.now().date() - timedelta(days=30))
            end_date = period.get("end", timezone.now().date())
            days = (end_date - start_date).days or 1
            
            total_consumed = StockTransaction.objects.filter(
                stock_item_id=item_id,
                movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            ).aggregate(total=Sum("base_quantity"))["total"] or Decimal("0")
            
            total_consumed = abs(total_consumed)
            daily_rate = total_consumed / days
            
            # Current stock
            current_stock = StockLevel.objects.filter(
                stock_item_id=item_id
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            
            # Days until stockout
            days_remaining = int(current_stock / daily_rate) if daily_rate > 0 else 999
            
            data.append({
                "item_name": item.name,
                "daily_rate": float(daily_rate),
                "weekly_rate": float(daily_rate * 7),
                "monthly_rate": float(daily_rate * 30),
                "current_stock": float(current_stock),
                "days_remaining": days_remaining,
                "unit": item.base_unit.short_name,
            })
        
        response = f"📈 **Consumption Rates ({period.get('text', 'last 30 days')}):**\n\n"
        
        for item in data:
            urgency = "🔴" if item["days_remaining"] < 7 else "🟡" if item["days_remaining"] < 14 else "🟢"
            response += f"**{item['item_name']}**\n"
            response += f"  Daily: {item['daily_rate']:,.2f} {item['unit']}/day\n"
            response += f"  Current: {item['current_stock']:,.2f} {item['unit']}\n"
            response += f"  {urgency} Runs out in: ~{item['days_remaining']} days\n\n"
        
        return {
            "response": response,
            "data": {"consumption_rates": data},
            "suggestions": [
                "Create purchase order for fast-moving items",
                "Show consumption trend",
                "Which days have highest usage?"
            ]
        }
    
    @classmethod
    def _handle_trend(cls, query: str, params: Dict) -> Dict:
        """Handle trend analysis queries"""
        items = params.get("items", [])
        period = params.get("period", {})
        location_id = params.get("location_id")
        
        # Default to last 30 days with weekly grouping
        start_date = period.get("start", timezone.now().date() - timedelta(days=30))
        end_date = period.get("end", timezone.now().date())
        
        queryset = StockTransaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        if items:
            queryset = queryset.filter(stock_item_id__in=[i["id"] for i in items])
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Group by week
        weekly_data = queryset.annotate(
            week=TruncWeek("created_at")
        ).values("week").annotate(
            total_in=Sum("base_quantity", filter=Q(base_quantity__gt=0)),
            total_out=Sum("base_quantity", filter=Q(base_quantity__lt=0)),
            transaction_count=Count("id")
        ).order_by("week")
        
        data = []
        for week in weekly_data:
            data.append({
                "week": week["week"].isoformat() if week["week"] else None,
                "total_in": float(week["total_in"] or 0),
                "total_out": abs(float(week["total_out"] or 0)),
                "net": float((week["total_in"] or 0) + (week["total_out"] or 0)),
                "transactions": week["transaction_count"],
            })
        
        # Calculate trend
        if len(data) >= 2:
            first_half = sum(d["total_out"] for d in data[:len(data)//2])
            second_half = sum(d["total_out"] for d in data[len(data)//2:])
            
            if first_half > 0:
                trend_pct = ((second_half - first_half) / first_half) * 100
                trend_direction = "📈 increasing" if trend_pct > 5 else "📉 decreasing" if trend_pct < -5 else "➡️ stable"
            else:
                trend_pct = 0
                trend_direction = "➡️ stable"
        else:
            trend_pct = 0
            trend_direction = "insufficient data"
        
        response = f"📊 **Stock Movement Trend ({period.get('text', 'last 30 days')}):**\n\n"
        response += f"Overall trend: {trend_direction} ({trend_pct:+.1f}%)\n\n"
        
        response += "**Weekly Breakdown:**\n"
        for week in data[-4:]:  # Last 4 weeks
            response += f"• Week of {week['week'][:10] if week['week'] else 'N/A'}: "
            response += f"IN: {week['total_in']:,.0f} | OUT: {week['total_out']:,.0f} | Net: {week['net']:+,.0f}\n"
        
        return {
            "response": response,
            "data": {"weekly_trend": data, "trend_percentage": trend_pct, "trend_direction": trend_direction},
            "suggestions": [
                "Compare to same period last year",
                "Show daily breakdown",
                "Which items are trending up?"
            ]
        }
    
    @classmethod
    def _handle_comparison(cls, query: str, params: Dict) -> Dict:
        """Handle comparison queries"""
        period = params.get("period", {})
        
        # Current period
        current_start = period.get("start", timezone.now().date() - timedelta(days=30))
        current_end = period.get("end", timezone.now().date())
        days = (current_end - current_start).days
        
        # Previous period (same length)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days)
        
        def get_period_stats(start, end):
            transactions = StockTransaction.objects.filter(
                created_at__date__gte=start,
                created_at__date__lte=end
            )
            
            return {
                "total_in": abs(float(transactions.filter(
                    base_quantity__gt=0
                ).aggregate(total=Sum("base_quantity"))["total"] or 0)),
                "total_out": abs(float(transactions.filter(
                    base_quantity__lt=0
                ).aggregate(total=Sum("base_quantity"))["total"] or 0)),
                "transaction_count": transactions.count(),
            }
        
        current_stats = get_period_stats(current_start, current_end)
        previous_stats = get_period_stats(previous_start, previous_end)
        
        # Calculate changes
        def calc_change(current, previous):
            if previous == 0:
                return 0 if current == 0 else 100
            return ((current - previous) / previous) * 100
        
        data = {
            "current_period": {
                "start": current_start.isoformat(),
                "end": current_end.isoformat(),
                "stats": current_stats,
            },
            "previous_period": {
                "start": previous_start.isoformat(),
                "end": previous_end.isoformat(),
                "stats": previous_stats,
            },
            "changes": {
                "in_change": calc_change(current_stats["total_in"], previous_stats["total_in"]),
                "out_change": calc_change(current_stats["total_out"], previous_stats["total_out"]),
                "transaction_change": calc_change(current_stats["transaction_count"], previous_stats["transaction_count"]),
            }
        }
        
        response = f"📊 **Period Comparison:**\n\n"
        response += f"**Current:** {current_start} to {current_end}\n"
        response += f"**Previous:** {previous_start} to {previous_end}\n\n"
        
        def change_emoji(pct):
            return "📈" if pct > 5 else "📉" if pct < -5 else "➡️"
        
        response += "**Stock IN:**\n"
        response += f"  Current: {current_stats['total_in']:,.0f} | Previous: {previous_stats['total_in']:,.0f}\n"
        response += f"  {change_emoji(data['changes']['in_change'])} Change: {data['changes']['in_change']:+.1f}%\n\n"
        
        response += "**Stock OUT:**\n"
        response += f"  Current: {current_stats['total_out']:,.0f} | Previous: {previous_stats['total_out']:,.0f}\n"
        response += f"  {change_emoji(data['changes']['out_change'])} Change: {data['changes']['out_change']:+.1f}%\n\n"
        
        response += "**Transactions:**\n"
        response += f"  Current: {current_stats['transaction_count']} | Previous: {previous_stats['transaction_count']}\n"
        response += f"  {change_emoji(data['changes']['transaction_change'])} Change: {data['changes']['transaction_change']:+.1f}%\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "What caused the increase/decrease?",
                "Compare specific item",
                "Show top changers"
            ]
        }
    
    @classmethod
    def _handle_forecast(cls, query: str, params: Dict) -> Dict:
        """Handle forecast queries"""
        items = params.get("items", [])
        location_id = params.get("location_id")
        
        # Get items to forecast
        if items:
            stock_items = StockItem.objects.filter(id__in=[i["id"] for i in items])
        else:
            # Top consumed items
            stock_items = StockItem.objects.filter(
                id__in=StockTransaction.objects.filter(
                    movement_type__in=["SALE_OUT", "PRODUCTION_OUT"]
                ).values("stock_item_id").annotate(
                    total=Sum("base_quantity")
                ).order_by("total")[:10].values_list("stock_item_id", flat=True)
            )
        
        data = []
        for item in stock_items:
            # Get 30-day consumption
            thirty_days_ago = timezone.now().date() - timedelta(days=30)
            
            consumption = StockTransaction.objects.filter(
                stock_item=item,
                movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
                created_at__date__gte=thirty_days_ago
            ).aggregate(total=Sum("base_quantity"))["total"] or Decimal("0")
            
            daily_consumption = abs(consumption) / 30
            
            # Current stock
            current = StockLevel.objects.filter(
                stock_item=item
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            
            # Days until stockout
            if daily_consumption > 0:
                days_until_stockout = int(current / daily_consumption)
                stockout_date = timezone.now().date() + timedelta(days=days_until_stockout)
            else:
                days_until_stockout = 999
                stockout_date = None
            
            # When to reorder (based on lead time and reorder point)
            lead_time = 7  # Default lead time
            safety_stock_days = 3
            
            if daily_consumption > 0:
                reorder_in_days = days_until_stockout - lead_time - safety_stock_days
                reorder_date = timezone.now().date() + timedelta(days=max(0, reorder_in_days))
            else:
                reorder_in_days = 999
                reorder_date = None
            
            data.append({
                "item_name": item.name,
                "current_stock": float(current),
                "daily_consumption": float(daily_consumption),
                "days_until_stockout": days_until_stockout,
                "stockout_date": stockout_date.isoformat() if stockout_date else None,
                "reorder_in_days": max(0, reorder_in_days),
                "reorder_date": reorder_date.isoformat() if reorder_date else None,
                "unit": item.base_unit.short_name,
                "status": "critical" if days_until_stockout < 7 else "warning" if days_until_stockout < 14 else "ok"
            })
        
        # Sort by urgency
        data.sort(key=lambda x: x["days_until_stockout"])
        
        response = "🔮 **Stock Forecast:**\n\n"
        
        for item in data[:10]:
            if item["status"] == "critical":
                emoji = "🔴"
            elif item["status"] == "warning":
                emoji = "🟡"
            else:
                emoji = "🟢"
            
            response += f"{emoji} **{item['item_name']}**\n"
            response += f"   Current: {item['current_stock']:,.2f} {item['unit']}\n"
            response += f"   Daily usage: {item['daily_consumption']:,.2f} {item['unit']}/day\n"
            
            if item["days_until_stockout"] < 999:
                response += f"   ⏰ Runs out in {item['days_until_stockout']} days ({item['stockout_date']})\n"
                if item["reorder_in_days"] <= 0:
                    response += f"   ⚠️ **REORDER NOW!**\n"
                else:
                    response += f"   📦 Reorder by: {item['reorder_date']}\n"
            else:
                response += f"   ✅ No consumption detected\n"
            response += "\n"
        
        return {
            "response": response,
            "data": {"forecasts": data},
            "suggestions": [
                "Create purchase order for critical items",
                "Show supplier options",
                "Adjust safety stock levels"
            ]
        }
    
    @classmethod
    def _handle_supplier_info(cls, query: str, params: Dict) -> Dict:
        """Handle supplier info queries"""
        suppliers = params.get("suppliers", [])
        
        if suppliers:
            supplier = Supplier.objects.filter(id=suppliers[0]["id"]).first()
            
            # Get supplier items
            items = SupplierStockItem.objects.filter(
                supplier=supplier
            ).select_related("stock_item", "unit")[:10]
            
            data = {
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name,
                    "contact": supplier.contact_person,
                    "phone": supplier.phone,
                    "email": supplier.email,
                    "payment_terms": supplier.payment_terms_days,
                    "lead_time": supplier.lead_time_days,
                    "balance": float(supplier.current_balance),
                },
                "items": [{
                    "item_name": si.stock_item.name,
                    "price": float(si.price),
                    "unit": si.unit.short_name,
                    "is_preferred": si.is_preferred,
                } for si in items]
            }
            
            response = f"🏢 **Supplier: {supplier.name}**\n\n"
            response += f"📞 Contact: {supplier.contact_person or 'N/A'}\n"
            response += f"📱 Phone: {supplier.phone or 'N/A'}\n"
            response += f"📧 Email: {supplier.email or 'N/A'}\n"
            response += f"💳 Payment terms: {supplier.payment_terms_days} days\n"
            response += f"🚚 Lead time: {supplier.lead_time_days} days\n"
            response += f"💰 Balance: {supplier.current_balance:,.0f} UZS\n\n"
            
            response += f"**Items ({len(data['items'])}):**\n"
            for item in data["items"]:
                star = "⭐" if item["is_preferred"] else ""
                response += f"  • {item['item_name']}: {item['price']:,.0f} UZS/{item['unit']} {star}\n"
        else:
            # List all suppliers
            suppliers = Supplier.objects.filter(is_active=True).order_by("name")
            
            data = [{
                "id": s.id,
                "name": s.name,
                "items_count": s.stock_items.count(),
                "balance": float(s.current_balance),
            } for s in suppliers[:20]]
            
            response = f"🏢 **Suppliers ({len(data)}):**\n\n"
            for s in data:
                response += f"• **{s['name']}** - {s['items_count']} items | Balance: {s['balance']:,.0f} UZS\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Show supplier's price list",
                "Compare suppliers for item",
                "Show pending orders from supplier"
            ]
        }
    
    @classmethod
    def _handle_best_supplier(cls, query: str, params: Dict) -> Dict:
        """Handle best supplier queries"""
        items = params.get("items", [])
        
        if not items:
            return {
                "response": "Please specify which item you want to find suppliers for.\n\nExample: 'Who's the best supplier for flour?'",
                "data": {},
                "suggestions": ["Best supplier for flour", "Cheapest vendor for sugar"]
            }
        
        item = StockItem.objects.filter(id=items[0]["id"]).first()
        
        supplier_items = SupplierStockItem.objects.filter(
            stock_item=item,
            supplier__is_active=True
        ).select_related("supplier", "unit").order_by("price")
        
        data = [{
            "supplier_name": si.supplier.name,
            "price": float(si.price),
            "unit": si.unit.short_name,
            "lead_time": si.lead_time_days or si.supplier.lead_time_days,
            "min_order": float(si.min_order_qty),
            "is_preferred": si.is_preferred,
        } for si in supplier_items]
        
        if data:
            response = f"💰 **Suppliers for {item.name}:**\n\n"
            
            cheapest = data[0]
            response += f"🏆 **Best Price:** {cheapest['supplier_name']}\n"
            response += f"   {cheapest['price']:,.0f} UZS/{cheapest['unit']}\n\n"
            
            response += "**All Options:**\n"
            for i, s in enumerate(data, 1):
                star = "⭐" if s["is_preferred"] else ""
                response += f"{i}. {s['supplier_name']} {star}\n"
                response += f"   Price: {s['price']:,.0f} UZS | Lead: {s['lead_time']} days | MOQ: {s['min_order']:,.0f}\n"
        else:
            response = f"No suppliers found for {item.name}. Consider adding supplier information."
        
        return {
            "response": response,
            "data": {"item": item.name, "suppliers": data},
            "suggestions": [
                f"Create PO from {data[0]['supplier_name']}" if data else "Add supplier",
                "Compare with similar items",
                "Show price history"
            ]
        }
    
    @classmethod
    def _handle_purchase_orders(cls, query: str, params: Dict) -> Dict:
        """Handle purchase order queries"""
        period = params.get("period", {})
        suppliers = params.get("suppliers", [])
        
        queryset = PurchaseOrder.objects.select_related("supplier", "delivery_location")
        
        if suppliers:
            queryset = queryset.filter(supplier_id__in=[s["id"] for s in suppliers])
        
        if period.get("start"):
            queryset = queryset.filter(order_date__gte=period["start"])
        
        # Group by status
        by_status = queryset.values("status").annotate(
            count=Count("id"),
            total=Sum("total")
        )
        
        recent = queryset.order_by("-order_date")[:10]
        
        data = {
            "by_status": {s["status"]: {"count": s["count"], "total": float(s["total"] or 0)} for s in by_status},
            "recent": [{
                "number": po.order_number,
                "supplier": po.supplier.name,
                "status": po.status,
                "total": float(po.total),
                "date": po.order_date.isoformat(),
            } for po in recent]
        }
        
        total_orders = sum(s["count"] for s in by_status)
        total_value = sum(s["total"] or 0 for s in by_status)
        
        response = f"📋 **Purchase Orders ({period.get('text', 'all')}):**\n\n"
        response += f"Total: {total_orders} orders | {total_value:,.0f} UZS\n\n"
        
        response += "**By Status:**\n"
        for status, info in data["by_status"].items():
            response += f"  • {status}: {info['count']} ({info['total']:,.0f} UZS)\n"
        
        response += "\n**Recent Orders:**\n"
        for po in data["recent"][:5]:
            emoji = "🟢" if po["status"] == "RECEIVED" else "🟡" if po["status"] in ["SENT", "CONFIRMED"] else "⚪"
            response += f"{emoji} {po['number']} | {po['supplier']} | {po['total']:,.0f} UZS | {po['status']}\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Show pending orders",
                "Create new purchase order",
                "Show overdue orders"
            ]
        }
    
    @classmethod
    def _handle_pending_orders(cls, query: str, params: Dict) -> Dict:
        """Handle pending orders queries"""
        pending = PurchaseOrder.objects.filter(
            status__in=["SENT", "CONFIRMED", "PARTIAL"]
        ).select_related("supplier").order_by("expected_date")
        
        data = [{
            "number": po.order_number,
            "supplier": po.supplier.name,
            "status": po.status,
            "total": float(po.total),
            "expected_date": po.expected_date.isoformat() if po.expected_date else None,
            "days_until": (po.expected_date - timezone.now().date()).days if po.expected_date else None,
        } for po in pending]
        
        response = f"📦 **Pending Deliveries ({len(data)} orders):**\n\n"
        
        for po in data:
            if po["days_until"] is not None:
                if po["days_until"] < 0:
                    timing = f"🔴 {abs(po['days_until'])} days OVERDUE"
                elif po["days_until"] == 0:
                    timing = "🟡 Expected TODAY"
                else:
                    timing = f"🟢 In {po['days_until']} days"
            else:
                timing = "📅 No date set"
            
            response += f"**{po['number']}** from {po['supplier']}\n"
            response += f"   {timing} | {po['total']:,.0f} UZS | {po['status']}\n\n"
        
        if not data:
            response = "✅ **No pending deliveries!** All orders have been received."
        
        return {
            "response": response,
            "data": {"pending_orders": data, "count": len(data)},
            "suggestions": [
                "Mark order as received",
                "Contact supplier about overdue",
                "Show order details"
            ]
        }
    
    @classmethod
    def _handle_production_info(cls, query: str, params: Dict) -> Dict:
        """Handle production info queries"""
        period = params.get("period", {})
        
        queryset = ProductionOrder.objects.select_related("recipe")
        
        if period.get("start"):
            queryset = queryset.filter(created_at__date__gte=period["start"])
        
        by_status = queryset.values("status").annotate(count=Count("id"))
        
        recent = queryset.order_by("-created_at")[:10]
        
        data = {
            "by_status": {s["status"]: s["count"] for s in by_status},
            "recent": [{
                "number": po.order_number,
                "recipe": po.recipe.name,
                "status": po.status,
                "expected_qty": float(po.expected_output_qty),
                "actual_qty": float(po.actual_output_qty) if po.actual_output_qty else None,
            } for po in recent]
        }
        
        response = f"🏭 **Production Orders ({period.get('text', 'all')}):**\n\n"
        
        response += "**By Status:**\n"
        for status, count in data["by_status"].items():
            emoji = "🟢" if status == "COMPLETED" else "🔵" if status == "IN_PROGRESS" else "⚪"
            response += f"  {emoji} {status}: {count}\n"
        
        response += "\n**Recent:**\n"
        for po in data["recent"][:5]:
            response += f"• {po['number']} | {po['recipe']} | {po['status']}\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Start production order",
                "Show recipe cost",
                "Check ingredient availability"
            ]
        }
    
    @classmethod
    def _handle_recipe_cost(cls, query: str, params: Dict) -> Dict:
        """Handle recipe cost queries"""
        # Find recipe
        match = re.search(r'(?:cost|price|make|produce)\s+(?:of\s+)?(.+?)(?:\?|$)', query, re.IGNORECASE)
        
        if match:
            recipe_name = match.group(1).strip()
            recipe = Recipe.objects.filter(
                Q(name__icontains=recipe_name) | Q(output_item__name__icontains=recipe_name),
                is_active=True
            ).first()
        else:
            recipe = None
        
        if recipe:
            # Calculate cost
            total_cost = Decimal("0")
            ingredients_data = []
            
            for ing in recipe.ingredients.select_related("stock_item", "unit"):
                item_cost = ing.stock_item.avg_cost_price * ing.quantity
                total_cost += item_cost
                
                ingredients_data.append({
                    "item": ing.stock_item.name,
                    "quantity": float(ing.quantity),
                    "unit": ing.unit.short_name,
                    "unit_cost": float(ing.stock_item.avg_cost_price),
                    "total_cost": float(item_cost),
                })
            
            cost_per_unit = total_cost / recipe.output_quantity if recipe.output_quantity > 0 else Decimal("0")
            
            data = {
                "recipe": recipe.name,
                "output_quantity": float(recipe.output_quantity),
                "output_unit": recipe.output_unit.short_name,
                "total_cost": float(total_cost),
                "cost_per_unit": float(cost_per_unit),
                "ingredients": ingredients_data,
            }
            
            response = f"💰 **Recipe Cost: {recipe.name}**\n\n"
            response += f"Output: {recipe.output_quantity} {recipe.output_unit.short_name}\n"
            response += f"**Total Cost: {total_cost:,.0f} UZS**\n"
            response += f"**Cost per unit: {cost_per_unit:,.0f} UZS/{recipe.output_unit.short_name}**\n\n"
            
            response += "**Ingredients:**\n"
            for ing in ingredients_data:
                response += f"  • {ing['item']}: {ing['quantity']} {ing['unit']} = {ing['total_cost']:,.0f} UZS\n"
        else:
            data = {}
            response = "Recipe not found. Please specify which recipe you want to check.\n\nExample: 'How much does it cost to make chocolate cake?'"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Check ingredient availability",
                "Start production order",
                "Compare with selling price"
            ]
        }
    
    @classmethod
    def _handle_search(cls, query: str, params: Dict) -> Dict:
        """Handle search queries"""
        # Extract search term
        match = re.search(r'(?:find|search|look for|where is)\s+(.+?)(?:\?|$)', query, re.IGNORECASE)
        search_term = match.group(1).strip() if match else query
        
        # Search items
        items = StockItem.objects.filter(
            Q(name__icontains=search_term) |
            Q(sku__icontains=search_term) |
            Q(barcode__icontains=search_term)
        )[:10]
        
        # Search suppliers
        suppliers = Supplier.objects.filter(
            Q(name__icontains=search_term) |
            Q(code__icontains=search_term)
        )[:5]
        
        # Search recipes
        recipes = Recipe.objects.filter(
            name__icontains=search_term
        )[:5]
        
        data = {
            "items": [{"id": i.id, "name": i.name, "sku": i.sku} for i in items],
            "suppliers": [{"id": s.id, "name": s.name} for s in suppliers],
            "recipes": [{"id": r.id, "name": r.name} for r in recipes],
        }
        
        response = f"🔍 **Search results for '{search_term}':**\n\n"
        
        if items:
            response += f"**Items ({len(items)}):**\n"
            for item in items:
                response += f"  • {item.name} ({item.sku})\n"
        
        if suppliers:
            response += f"\n**Suppliers ({len(suppliers)}):**\n"
            for s in suppliers:
                response += f"  • {s.name}\n"
        
        if recipes:
            response += f"\n**Recipes ({len(recipes)}):**\n"
            for r in recipes:
                response += f"  • {r.name}\n"
        
        if not any([items, suppliers, recipes]):
            response += "No results found. Try a different search term."
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                f"Show stock for {items[0].name}" if items else "Add new item",
                "Search by barcode",
                "List all items"
            ]
        }
    
    @classmethod
    def _handle_help(cls, query: str, params: Dict) -> Dict:
        """Handle help queries"""
        response = """🤖 **Stock Assistant - Help**

I can help you with:

📦 **Stock Levels**
• "How much flour do we have?"
• "Show low stock items"
• "What's out of stock?"
• "Total inventory value"

📊 **Analytics**
• "Top 10 most used items"
• "Consumption rate for sugar"
• "Stock trend this month"
• "Compare this week vs last week"

⏰ **Batches & Expiry**
• "What's expiring this week?"
• "Show expired batches"
• "Forecast when items run out"

🏢 **Suppliers**
• "List suppliers"
• "Best supplier for flour"
• "Pending deliveries"

📋 **Orders**
• "Show purchase orders"
• "Production status"
• "Recipe cost for pizza"

💡 **Tips:**
• Specify time periods: "last week", "this month", "last 7 days"
• Specify items: "stock of flour", "sugar consumption"
• Specify locations: "at warehouse", "in kitchen"
"""
        
        return {
            "response": response,
            "data": {"capabilities": list(cls.INTENT_PATTERNS.keys())},
            "suggestions": [
                "Show stock overview",
                "Low stock alerts",
                "What's expiring soon?"
            ]
        }
    
    @classmethod
    def _handle_summary(cls, query: str, params: Dict) -> Dict:
        """Handle summary/dashboard queries"""
        # Gather key metrics
        today = timezone.now().date()
        
        # Stock value
        stock_value = sum(
            float(l.quantity * l.stock_item.avg_cost_price)
            for l in StockLevel.objects.filter(quantity__gt=0).select_related("stock_item")
        )
        
        # Low stock count
        low_stock = StockLevel.objects.filter(
            quantity__lte=F("stock_item__reorder_point")
        ).count()
        
        # Expiring soon
        expiring = StockBatch.objects.filter(
            expiry_date__lte=today + timedelta(days=7),
            expiry_date__gt=today,
            current_quantity__gt=0
        ).count()
        
        # Today's transactions
        today_transactions = StockTransaction.objects.filter(
            created_at__date=today
        ).count()
        
        # Pending POs
        pending_pos = PurchaseOrder.objects.filter(
            status__in=["SENT", "CONFIRMED", "PARTIAL"]
        ).count()
        
        # Active production
        active_production = ProductionOrder.objects.filter(
            status="IN_PROGRESS"
        ).count()
        
        data = {
            "stock_value": stock_value,
            "low_stock_count": low_stock,
            "expiring_soon": expiring,
            "today_transactions": today_transactions,
            "pending_pos": pending_pos,
            "active_production": active_production,
        }
        
        response = "📊 **Stock Dashboard**\n\n"
        
        response += f"💰 **Inventory Value:** {stock_value:,.0f} UZS\n\n"
        
        # Alerts section
        alerts = []
        if low_stock > 0:
            alerts.append(f"⚠️ {low_stock} items below reorder level")
        if expiring > 0:
            alerts.append(f"⏰ {expiring} batches expiring in 7 days")
        
        if alerts:
            response += "**🔔 Alerts:**\n"
            for alert in alerts:
                response += f"  {alert}\n"
            response += "\n"
        else:
            response += "✅ **No alerts!** Everything looks good.\n\n"
        
        response += "**📈 Today's Activity:**\n"
        response += f"  • Transactions: {today_transactions}\n"
        response += f"  • Pending POs: {pending_pos}\n"
        response += f"  • Active Production: {active_production}\n"
        
        return {
            "response": response,
            "data": data,
            "suggestions": [
                "Show low stock items",
                "What's expiring?",
                "Show pending orders"
            ]
        }
    
    @classmethod
    def _handle_unknown(cls, query: str, params: Dict) -> Dict:
        """Handle unknown queries"""
        return {
            "response": f"I'm not sure I understood that. Here's what I can help with:\n\n"
                       f"• Stock levels and inventory value\n"
                       f"• Low stock and expiring items alerts\n"
                       f"• Consumption trends and forecasts\n"
                       f"• Supplier and purchase order info\n"
                       f"• Production and recipe costs\n\n"
                       f"Try asking something like:\n"
                       f"• 'How much flour do we have?'\n"
                       f"• 'Show low stock items'\n"
                       f"• 'What's expiring this week?'\n\n"
                       f"Or type 'help' for more options.",
            "data": {},
            "suggestions": [
                "Help",
                "Stock overview",
                "Low stock items"
            ]
        }
