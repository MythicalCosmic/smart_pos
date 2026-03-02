import google.generativeai as genai
from typing import Dict, Any, List
from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.conf import settings
import json

from stock.models import (
    StockItem, StockLevel, StockTransaction, StockBatch,
    StockLocation, Supplier, SupplierStockItem,
    PurchaseOrder, Recipe, ProductionOrder
)


SYSTEM_PROMPT = """You are an expert stock management AI assistant for a restaurant/retail POS system in Uzbekistan.

=== LANGUAGE RULES ===
- DETECT user's language automatically from their query
- If Cyrillic letters (а-я, А-Я) -> respond in RUSSIAN
- If Uzbek words (qancha, bor, qoldi, ombor, mahsulot, narx, kerak, yetarli, kam, zaxira, mavjud, eskirgan, yetkazib, buyurtma, tovar, oshxona) -> respond in UZBEK
- Otherwise -> respond in ENGLISH
- NEVER mix languages in one response

=== FORMATTING RULES ===
- NO emojis ever
- Format numbers: 1,000 not 1000
- Always show units: kg, g, pcs/dona/sht, litr
- Currency: UZS (O'zbek so'mi / Узбекский сум)
- Dates: YYYY-MM-DD format
- Use simple text formatting with dashes and line breaks
- Keep responses concise but complete

=== YOUR CAPABILITIES ===
You can answer ANY question about:
1. Stock levels - current quantities, locations, values
2. Low stock alerts - items below reorder point
3. Expiring/expired batches - shelf life management
4. Consumption analysis - usage rates, trends, patterns
5. Forecasting - predict stockouts, suggest reorder dates
6. Suppliers - pricing, lead times, comparisons
7. Purchase orders - status, pending deliveries
8. Recipes - ingredient costs, availability checks
9. Transactions - movement history, in/out analysis
10. General inventory advice and recommendations

=== PREDICTION METHODOLOGY ===
When forecasting stockouts, ALWAYS show your calculation:
1. daily_usage = total_consumed_in_period / number_of_days
2. days_remaining = current_stock / daily_usage
3. stockout_date = today + days_remaining
4. reorder_by = stockout_date - lead_time - 3_days_safety

Example:
"Flour: 5,000g current, 250g/day usage
Calculation: 5000 / 250 = 20 days
Stockout: 2026-03-22
Lead time: 7 days, Safety: 3 days
Reorder by: 2026-03-12"

=== RESPONSE STRUCTURE ===
1. Direct answer first (the specific info they asked for)
2. Relevant supporting data
3. 2-3 actionable recommendations

=== HANDLING MISSING DATA ===
- If data is empty/null, say "No data available for X"
- If item not found, suggest similar items or ask for clarification
- Never invent or assume data that isn't provided

=== SAMPLE RESPONSES ===

ENGLISH - "How much flour do we have?"
---
FLOUR STOCK

Current: 5,000 g total
- Main Warehouse: 3,000 g
- Kitchen: 2,000 g

Status: LOW (below 6,000 g reorder point)

Recommendations:
- Order within 3 days
- Check supplier availability
---

RUSSIAN - "Сколько муки?"
---
ОСТАТОК МУКИ

Всего: 5 000 г
- Основной склад: 3 000 г
- Кухня: 2 000 г

Статус: НИЗКИЙ (ниже точки заказа 6 000 г)

Рекомендации:
- Закажите в течение 3 дней
- Уточните наличие у поставщика
---

UZBEK - "Qancha un bor?"
---
UN QOLDIG'I

Jami: 5 000 g
- Asosiy ombor: 3 000 g
- Oshxona: 2 000 g

Holat: KAM (6 000 g buyurtma nuqtasidan past)

Tavsiyalar:
- 3 kun ichida buyurtma bering
- Yetkazib beruvchidan tekshiring
---

You will receive real-time database data in JSON format. Analyze it and respond accurately based ONLY on the provided data."""


class AIStockAssistant:

    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            # api_key = getattr(settings, 'GEMINI_API_KEY', None)
            api_key = 'AIzaSyDq60ysKtvM1QzrKIw6evUtkbYWtUkv2ko'
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")
            genai.configure(api_key=api_key)
            cls._model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config={"temperature": 0.1, "max_output_tokens": 2048}
            )
        return cls._model

    @classmethod
    def _get_all_stock_data(cls) -> Dict:
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        
        levels = StockLevel.objects.filter(
            stock_item__is_active=True
        ).select_related("stock_item", "location", "stock_item__base_unit")
        
        stock_items = []
        total_value = 0
        low_stock = []
        out_of_stock = []
        
        for level in levels:
            item = level.stock_item
            qty = float(level.quantity)
            value = qty * float(item.avg_cost_price)
            total_value += value
            
            item_data = {
                "name": item.name,
                "sku": item.sku,
                "location": level.location.name,
                "quantity": qty,
                "reserved": float(level.reserved_quantity),
                "available": qty - float(level.reserved_quantity),
                "unit": item.base_unit.short_name,
                "reorder_point": float(item.reorder_point),
                "min_level": float(item.min_stock_level),
                "avg_cost_uzs": float(item.avg_cost_price),
                "value_uzs": value,
                "is_low": qty <= float(item.reorder_point),
                "is_out": qty <= 0
            }
            stock_items.append(item_data)
            
            if qty <= float(item.reorder_point) and qty > 0:
                low_stock.append(item_data)
            if qty <= 0:
                out_of_stock.append(item_data)
        
        expiring = StockBatch.objects.filter(
            expiry_date__lte=today + timedelta(days=14),
            expiry_date__gt=today,
            current_quantity__gt=0
        ).select_related("stock_item", "location")[:30]
        
        expiring_batches = [{
            "item": b.stock_item.name,
            "batch": b.batch_number,
            "quantity": float(b.current_quantity),
            "unit": b.stock_item.base_unit.short_name,
            "location": b.location.name,
            "expiry_date": b.expiry_date.isoformat(),
            "days_left": (b.expiry_date - today).days,
            "value_uzs": float(b.current_quantity * b.unit_cost)
        } for b in expiring]
        
        expired = StockBatch.objects.filter(
            expiry_date__lt=today,
            current_quantity__gt=0
        ).select_related("stock_item", "location")[:20]
        
        expired_batches = [{
            "item": b.stock_item.name,
            "batch": b.batch_number,
            "quantity": float(b.current_quantity),
            "unit": b.stock_item.base_unit.short_name,
            "location": b.location.name,
            "expiry_date": b.expiry_date.isoformat(),
            "days_expired": (today - b.expiry_date).days,
            "loss_uzs": float(b.current_quantity * b.unit_cost)
        } for b in expired]
        
        consumption = StockTransaction.objects.filter(
            movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
            created_at__date__gte=thirty_days_ago
        ).values("stock_item__name", "stock_item__base_unit__short_name").annotate(
            total=Sum("base_quantity"),
            count=Count("id")
        ).order_by("total")[:30]
        
        consumption_data = [{
            "item": c["stock_item__name"],
            "unit": c["stock_item__base_unit__short_name"],
            "total_30_days": abs(float(c["total"] or 0)),
            "daily_avg": abs(float(c["total"] or 0)) / 30,
            "transactions": c["count"]
        } for c in consumption]
        
        forecasts = []
        for c in consumption_data:
            item_levels = [s for s in stock_items if s["name"] == c["item"]]
            if item_levels and c["daily_avg"] > 0:
                current = sum(s["quantity"] for s in item_levels)
                days = int(current / c["daily_avg"]) if c["daily_avg"] > 0 else 999
                forecasts.append({
                    "item": c["item"],
                    "current_stock": current,
                    "unit": c["unit"],
                    "daily_usage": c["daily_avg"],
                    "days_until_stockout": days,
                    "stockout_date": (today + timedelta(days=days)).isoformat() if days < 999 else None,
                    "reorder_by": (today + timedelta(days=max(0, days - 10))).isoformat() if days < 999 else None
                })
        forecasts.sort(key=lambda x: x["days_until_stockout"])
        
        suppliers = Supplier.objects.filter(is_active=True)[:20]
        supplier_data = []
        for s in suppliers:
            items = SupplierStockItem.objects.filter(supplier=s).select_related("stock_item", "unit")[:10]
            supplier_data.append({
                "name": s.name,
                "contact": s.contact_person,
                "phone": s.phone,
                "lead_time_days": s.lead_time_days,
                "items": [{
                    "item": si.stock_item.name,
                    "price_uzs": float(si.price),
                    "unit": si.unit.short_name,
                    "preferred": si.is_preferred
                } for si in items]
            })
        
        pending_pos = PurchaseOrder.objects.filter(
            status__in=["SENT", "CONFIRMED", "PARTIAL"]
        ).select_related("supplier")[:15]
        
        purchase_orders = [{
            "number": po.order_number,
            "supplier": po.supplier.name,
            "status": po.status,
            "total_uzs": float(po.total),
            "order_date": po.order_date.isoformat(),
            "expected": po.expected_date.isoformat() if po.expected_date else None
        } for po in pending_pos]
        
        recipes = Recipe.objects.filter(is_active=True).prefetch_related("ingredients__stock_item", "ingredients__unit")[:15]
        recipe_data = []
        for r in recipes:
            ingredients = []
            total_cost = 0
            for ing in r.ingredients.all():
                cost = float(ing.stock_item.avg_cost_price * ing.quantity)
                total_cost += cost
                avail = StockLevel.objects.filter(stock_item=ing.stock_item).aggregate(t=Sum("quantity"))["t"] or 0
                ingredients.append({
                    "item": ing.stock_item.name,
                    "qty": float(ing.quantity),
                    "unit": ing.unit.short_name,
                    "cost_uzs": cost,
                    "available": float(avail),
                    "enough": float(avail) >= float(ing.quantity)
                })
            recipe_data.append({
                "name": r.name,
                "output_qty": float(r.output_quantity),
                "output_unit": r.output_unit.short_name if r.output_unit else "",
                "total_cost_uzs": total_cost,
                "cost_per_unit_uzs": total_cost / float(r.output_quantity) if r.output_quantity else 0,
                "ingredients": ingredients,
                "can_produce": all(i["enough"] for i in ingredients)
            })
        
        locations = list(StockLocation.objects.values("name", "type"))
        
        return {
            "date": today.isoformat(),
            "summary": {
                "total_items": len(stock_items),
                "total_value_uzs": total_value,
                "low_stock_count": len(low_stock),
                "out_of_stock_count": len(out_of_stock),
                "expiring_14_days": len(expiring_batches),
                "expired_count": len(expired_batches),
                "pending_orders": len(purchase_orders)
            },
            "stock_items": stock_items[:50],
            "low_stock_items": low_stock[:20],
            "out_of_stock_items": out_of_stock[:20],
            "expiring_batches": expiring_batches,
            "expired_batches": expired_batches,
            "consumption_30_days": consumption_data,
            "forecasts": forecasts[:20],
            "suppliers": supplier_data,
            "pending_purchase_orders": purchase_orders,
            "recipes": recipe_data,
            "locations": locations
        }

    @classmethod
    def process_query(cls, query: str, context: Dict = None, user_id: int = None, location_id: int = None) -> Dict[str, Any]:
        try:
            data = cls._get_all_stock_data()
            
            prompt = f"""USER QUERY: {query}

CURRENT DATABASE STATE:
{json.dumps(data, indent=2, default=str, ensure_ascii=False)}

Respond to the user's query based on this data. Follow all language and formatting rules from your instructions."""

            model = cls._get_model()
            response = model.generate_content(SYSTEM_PROMPT + "\n\n" + prompt)
            
            return {
                "success": True,
                "response": response.text,
                "suggestions": cls._get_suggestions(query)
            }
            
        except Exception as e:
            error_str = str(e)
            
            if "429" in error_str or "quota" in error_str.lower():
                return {
                    "success": False,
                    "error": "quota_exceeded",
                    "response": "API quota exceeded. Please enable billing at https://ai.google.dev or wait for quota reset.",
                    "suggestions": ["Check API billing", "Try again later"]
                }
            
            if "API_KEY" in error_str or "not set" in error_str:
                return {
                    "success": False,
                    "error": "no_api_key",
                    "response": "GEMINI_API_KEY not configured in Django settings.",
                    "suggestions": ["Add GEMINI_API_KEY to settings.py"]
                }
            
            return {
                "success": False,
                "error": error_str,
                "response": f"Error: {error_str}",
                "suggestions": ["Try again", "Stock overview"]
            }

    @classmethod
    def _get_suggestions(cls, query: str) -> List[str]:
        q = query.lower()
        if any(w in q for w in ["а", "е", "и", "о", "у", "ы", "э", "ю", "я"]):
            return ["Низкие запасы", "Что истекает?", "Прогноз"]
        if any(w in q for w in ["qancha", "qoldi", "bor", "ombor"]):
            return ["Kam zaxiralar", "Eskirayotganlar", "Bashorat"]
        return ["Low stock items", "What is expiring?", "Stock forecast"]


__all__ = ['AIStockAssistant']