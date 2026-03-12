import google.generativeai as genai
from typing import Dict, Any, List
from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum, Count, F, Q, Avg, Max, Min
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from django.conf import settings
import json

from stock.models import (
    StockItem, StockLevel, StockTransaction, StockBatch,
    StockLocation, Supplier, SupplierStockItem,
    PurchaseOrder, Recipe, ProductionOrder
)

from main.models import (
    User, Order, OrderItem, Product, Category,
    CashRegister, Inkassa, Session
)


SYSTEM_PROMPT = """You are an expert AI assistant for a restaurant/retail POS system in Uzbekistan.
You have full access to BOTH sales/business data AND stock/inventory data.

=== LANGUAGE RULES ===
- DETECT user's language automatically from their query
- If Cyrillic letters (а-я, А-Я) -> respond in RUSSIAN
- If Uzbek words (qancha, bor, qoldi, ombor, mahsulot, narx, kerak, yetarli, kam, zaxira, mavjud, eskirgan, yetkazib, buyurtma, tovar, oshxona, sotuv, kassir, foyda) -> respond in UZBEK
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

SALES & BUSINESS:
1. Sales data - today's revenue, total orders, order breakdown by type
2. Cashier performance - who sold the most, order counts per cashier, average order values
3. Best/worst products - top sellers, least sellers, revenue by product
4. Category analytics - revenue per category, popular categories
5. Order trends - hourly/daily/weekly patterns, peak hours
6. User management - how many users, roles, active/suspended
7. Cash register - current balance, inkassa history
8. Payment analysis - paid vs unpaid, order completion rates
9. Customer orders - order types (hall/delivery/pickup) distribution
10. Session activity - active sessions, recent logins

STOCK & INVENTORY:
11. Stock levels - current quantities, locations, values
12. Low stock alerts - items below reorder point
13. Expiring/expired batches - shelf life management
14. Consumption analysis - usage rates, trends, patterns
15. Forecasting - predict stockouts, suggest reorder dates
16. Suppliers - pricing, lead times, comparisons
17. Purchase orders - status, pending deliveries
18. Recipes - ingredient costs, availability checks
19. Transactions - movement history, in/out analysis
20. General inventory advice and recommendations

=== PREDICTION METHODOLOGY ===
When forecasting stockouts, ALWAYS show your calculation:
1. daily_usage = total_consumed_in_period / number_of_days
2. days_remaining = current_stock / daily_usage
3. stockout_date = today + days_remaining
4. reorder_by = stockout_date - lead_time - 3_days_safety

=== RESPONSE STRUCTURE ===
1. Direct answer first (the specific info they asked for)
2. Relevant supporting data
3. 2-3 actionable recommendations

=== HANDLING MISSING DATA ===
- If data is empty/null, say "No data available for X"
- If item not found, suggest similar items or ask for clarification
- Never invent or assume data that isn't provided

You will receive real-time database data in JSON format. Analyze it and respond accurately based ONLY on the provided data."""


class AIStockAssistant:

    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            api_key = 'AIzaSyDo4C4bue_fBoAqHg39ui9E2veJR3lOVaM'
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")
            genai.configure(api_key=api_key)
            cls._model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config={"temperature": 0.1, "max_output_tokens": 2048}
            )
        return cls._model

    @classmethod
    def _get_sales_data(cls) -> Dict:
        """Gather all sales, users, cashier, and business data from the main app."""
        now = timezone.now()
        today = now.date()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        # ── Orders summary ──
        all_orders = Order.objects.filter(is_deleted=False)
        today_orders = all_orders.filter(created_at__gte=today_start)
        week_orders = all_orders.filter(created_at__date__gte=seven_days_ago)
        month_orders = all_orders.filter(created_at__date__gte=thirty_days_ago)

        def order_stats(qs):
            agg = qs.aggregate(
                count=Count('id'),
                total_revenue=Sum('total_amount'),
                avg_order=Avg('total_amount'),
                paid_count=Count('id', filter=Q(is_paid=True)),
                unpaid_count=Count('id', filter=Q(is_paid=False)),
            )
            by_status = dict(qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c'))
            by_type = dict(qs.values_list('order_type').annotate(c=Count('id')).values_list('order_type', 'c'))
            return {
                "count": agg['count'] or 0,
                "total_revenue_uzs": float(agg['total_revenue'] or 0),
                "avg_order_uzs": float(agg['avg_order'] or 0),
                "paid": agg['paid_count'] or 0,
                "unpaid": agg['unpaid_count'] or 0,
                "by_status": by_status,
                "by_type": by_type,
            }

        # ── Top products (30 days) ──
        top_products = list(
            OrderItem.objects.filter(
                order__is_deleted=False,
                order__created_at__date__gte=thirty_days_ago
            ).values('product__name', 'product__price').annotate(
                qty_sold=Sum('quantity'),
                revenue=Sum(F('quantity') * F('price'))
            ).order_by('-revenue')[:15]
        )
        top_products_data = [{
            "name": p['product__name'],
            "unit_price_uzs": float(p['product__price']),
            "qty_sold": p['qty_sold'],
            "revenue_uzs": float(p['revenue'] or 0),
        } for p in top_products]

        # ── Top products TODAY ──
        top_products_today = list(
            OrderItem.objects.filter(
                order__is_deleted=False,
                order__created_at__gte=today_start
            ).values('product__name').annotate(
                qty_sold=Sum('quantity'),
                revenue=Sum(F('quantity') * F('price'))
            ).order_by('-revenue')[:10]
        )
        top_products_today_data = [{
            "name": p['product__name'],
            "qty_sold": p['qty_sold'],
            "revenue_uzs": float(p['revenue'] or 0),
        } for p in top_products_today]

        # ── Category revenue (30 days) ──
        category_revenue = list(
            OrderItem.objects.filter(
                order__is_deleted=False,
                order__created_at__date__gte=thirty_days_ago
            ).values('product__category__name').annotate(
                revenue=Sum(F('quantity') * F('price')),
                qty_sold=Sum('quantity')
            ).order_by('-revenue')[:10]
        )
        category_data = [{
            "category": c['product__category__name'],
            "revenue_uzs": float(c['revenue'] or 0),
            "qty_sold": c['qty_sold'],
        } for c in category_revenue]

        # ── Cashier performance (30 days) ──
        cashier_stats = list(
            all_orders.filter(
                cashier__isnull=False,
                created_at__date__gte=thirty_days_ago
            ).values(
                'cashier__id', 'cashier__first_name', 'cashier__last_name'
            ).annotate(
                orders_count=Count('id'),
                total_revenue=Sum('total_amount'),
                avg_order=Avg('total_amount'),
                completed=Count('id', filter=Q(status='COMPLETED')),
                canceled=Count('id', filter=Q(status='CANCELED')),
            ).order_by('-total_revenue')
        )
        cashier_data = [{
            "name": f"{c['cashier__first_name']} {c['cashier__last_name']}",
            "orders": c['orders_count'],
            "revenue_uzs": float(c['total_revenue'] or 0),
            "avg_order_uzs": float(c['avg_order'] or 0),
            "completed": c['completed'],
            "canceled": c['canceled'],
        } for c in cashier_stats]

        # ── Hourly distribution today ──
        hourly = list(
            today_orders.annotate(
                hour=TruncHour('created_at')
            ).values('hour').annotate(
                count=Count('id'),
                revenue=Sum('total_amount')
            ).order_by('hour')
        )
        hourly_data = [{
            "hour": h['hour'].strftime('%H:%M') if h['hour'] else '',
            "orders": h['count'],
            "revenue_uzs": float(h['revenue'] or 0),
        } for h in hourly]

        # ── Daily trend (7 days) ──
        daily_trend = list(
            week_orders.annotate(
                day=TruncDate('created_at')
            ).values('day').annotate(
                count=Count('id'),
                revenue=Sum('total_amount')
            ).order_by('day')
        )
        daily_data = [{
            "date": d['day'].isoformat() if d['day'] else '',
            "orders": d['count'],
            "revenue_uzs": float(d['revenue'] or 0),
        } for d in daily_trend]

        # ── Users ──
        user_counts = User.objects.filter(is_deleted=False).aggregate(
            total=Count('id'),
            admins=Count('id', filter=Q(role='ADMIN')),
            cashiers=Count('id', filter=Q(role='CASHIER')),
            users=Count('id', filter=Q(role='USER')),
            active=Count('id', filter=Q(status='ACTIVE')),
            suspended=Count('id', filter=Q(status='SUSPENDED')),
        )

        # ── Active sessions ──
        active_sessions = Session.objects.count()
        recent_logins = list(
            User.objects.filter(
                is_deleted=False,
                last_login_at__isnull=False
            ).order_by('-last_login_at').values(
                'first_name', 'last_name', 'role', 'last_login_at'
            )[:5]
        )
        recent_login_data = [{
            "name": f"{u['first_name']} {u['last_name']}",
            "role": u['role'],
            "last_login": u['last_login_at'].isoformat() if u['last_login_at'] else None,
        } for u in recent_logins]

        # ── Cash register ──
        cash = CashRegister.objects.first()
        cash_balance = float(cash.current_balance) if cash else 0

        # ── Inkassa (recent) ──
        recent_inkassa = list(
            Inkassa.objects.filter(is_deleted=False).order_by('-created_at').values(
                'cashier__first_name', 'cashier__last_name',
                'amount', 'inkass_type', 'balance_before', 'balance_after',
                'total_orders', 'total_revenue', 'created_at'
            )[:5]
        )
        inkassa_data = [{
            "cashier": f"{i['cashier__first_name']} {i['cashier__last_name']}",
            "amount_uzs": float(i['amount']),
            "type": i['inkass_type'],
            "balance_before_uzs": float(i['balance_before']),
            "balance_after_uzs": float(i['balance_after']),
            "orders_in_shift": i['total_orders'],
            "shift_revenue_uzs": float(i['total_revenue']),
            "date": i['created_at'].isoformat() if i['created_at'] else None,
        } for i in recent_inkassa]

        # ── Products & Categories count ──
        products_count = Product.objects.filter(is_deleted=False).count()
        categories_count = Category.objects.filter(is_deleted=False, status='ACTIVE').count()

        return {
            "today": order_stats(today_orders),
            "this_week": order_stats(week_orders),
            "this_month": order_stats(month_orders),
            "top_products_30_days": top_products_data,
            "top_products_today": top_products_today_data,
            "category_revenue": category_data,
            "cashier_performance": cashier_data,
            "hourly_today": hourly_data,
            "daily_trend_7_days": daily_data,
            "users": user_counts,
            "active_sessions": active_sessions,
            "recent_logins": recent_login_data,
            "cash_register_balance_uzs": cash_balance,
            "recent_inkassa": inkassa_data,
            "total_products": products_count,
            "total_categories": categories_count,
        }

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
            stock_data = cls._get_all_stock_data()
            sales_data = cls._get_sales_data()

            combined_data = {
                "date": timezone.now().date().isoformat(),
                "sales_and_business": sales_data,
                "stock_and_inventory": stock_data,
            }

            prompt = f"""USER QUERY: {query}

CURRENT DATABASE STATE:
{json.dumps(combined_data, indent=2, default=str, ensure_ascii=False)}

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
            return ["Низкие запасы", "Продажи за сегодня", "Лучший кассир"]
        if any(w in q for w in ["qancha", "qoldi", "bor", "ombor", "sotuv"]):
            return ["Kam zaxiralar", "Bugungi sotuvlar", "Eng yaxshi kassir"]
        return ["Low stock items", "Today's sales", "Best cashier", "Stock forecast"]


__all__ = ['AIStockAssistant']
