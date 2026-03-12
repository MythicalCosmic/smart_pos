import google.generativeai as genai
from typing import Dict, Any, List
from decimal import Decimal
from datetime import timedelta
import math
from django.db.models import Sum, Count, F, Q, Avg, Max, Min, StdDev, Variance
from django.db.models.functions import TruncDate, TruncHour, TruncWeek, TruncMonth
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


SYSTEM_PROMPT = """You are an expert AI business analyst and assistant for a restaurant/retail POS system in Uzbekistan.
You have full access to sales data, stock/inventory data, AND pre-computed business analytics.

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

SALES & BUSINESS:
1. Sales data - today's revenue, total orders, order breakdown by type
2. Cashier performance - who sold the most, order counts per cashier
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

BUSINESS ANALYTICS (pre-computed, in the data):
20. ABC Analysis - items classified by consumption value (A=top 80% value, B=next 15%, C=bottom 5%)
21. XYZ Analysis - items classified by demand predictability (X=stable CV<0.5, Y=variable CV 0.5-1.0, Z=unpredictable CV>1.0)
22. ABC-XYZ Matrix - combined classification for optimal strategy:
    - AX: high value + stable demand -> JIT purchasing, tight monitoring
    - AY: high value + variable demand -> moderate safety stock
    - AZ: high value + unpredictable -> high safety stock, careful forecasting
    - BX/BY/BZ: medium priority variants
    - CX: low value + stable -> automate reordering
    - CY/CZ: low value + unpredictable -> consider discontinuing or minimum stock
23. Menu Engineering (BCG Matrix for menu) - products classified by popularity and profitability:
    - Stars: high popularity + high margin -> promote and protect
    - Plow Horses: high popularity + low margin -> increase prices or reduce cost
    - Puzzles: low popularity + high margin -> promote more, reposition
    - Dogs: low popularity + low margin -> consider removing from menu
24. Profitability Analysis - gross margin per product (selling price vs ingredient cost via recipes)
25. Inventory Health - turnover ratio, days of supply, dead stock, carrying cost
26. Sales Velocity - revenue and quantity trends per product
27. Waste Analysis - spoilage and waste as % of total consumption

=== PREDICTION METHODOLOGY ===
When forecasting stockouts, ALWAYS show your calculation:
1. daily_usage = total_consumed_in_period / number_of_days
2. days_remaining = current_stock / daily_usage
3. stockout_date = today + days_remaining
4. reorder_by = stockout_date - lead_time - 3_days_safety

=== BUSINESS RECOMMENDATIONS ===
When giving business advice, base it on the analytics data provided:
- Reference specific ABC/XYZ classifications
- Use menu engineering categories to suggest menu changes
- Use profitability data to suggest pricing changes
- Use inventory turnover to suggest purchasing changes
- Always back recommendations with numbers from the data
- Prioritize actionable, specific recommendations over generic advice

=== RESPONSE STRUCTURE ===
1. Direct answer first (the specific info they asked for)
2. Relevant supporting data with numbers
3. 2-3 actionable recommendations backed by data

=== HANDLING MISSING DATA ===
- If data is empty/null, say "No data available for X"
- If item not found, suggest similar items or ask for clarification
- Never invent or assume data that isn't provided

You will receive real-time database data in JSON format including pre-computed analytics. Analyze it and respond accurately based ONLY on the provided data."""


class AIStockAssistant:

    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            api_key = settings.GEMINI_API_KEY
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
    def _get_abc_analysis(cls, days: int = 30) -> List[Dict]:
        """ABC Analysis: classify stock items by consumption value.
        A = top items contributing to 80% of total value
        B = next items contributing to 15%
        C = remaining items contributing to 5%
        """
        cutoff = timezone.now().date() - timedelta(days=days)

        consumption = StockTransaction.objects.filter(
            movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
            created_at__date__gte=cutoff
        ).values(
            "stock_item__id", "stock_item__name", "stock_item__sku",
            "stock_item__base_unit__short_name"
        ).annotate(
            total_qty=Sum("base_quantity"),
            total_cost=Sum("total_cost"),
            tx_count=Count("id")
        ).order_by("total_cost")

        items = []
        for c in consumption:
            items.append({
                "id": c["stock_item__id"],
                "name": c["stock_item__name"],
                "sku": c["stock_item__sku"],
                "unit": c["stock_item__base_unit__short_name"],
                "total_qty": abs(float(c["total_qty"] or 0)),
                "total_value_uzs": abs(float(c["total_cost"] or 0)),
                "transactions": c["tx_count"],
            })

        grand_total = sum(i["total_value_uzs"] for i in items)
        if grand_total == 0:
            return []

        items.sort(key=lambda x: x["total_value_uzs"], reverse=True)

        cumulative = 0
        for item in items:
            item["pct_of_total"] = round(item["total_value_uzs"] / grand_total * 100, 2)
            cumulative += item["pct_of_total"]
            item["cumulative_pct"] = round(cumulative, 2)

            if cumulative <= 80:
                item["abc_class"] = "A"
            elif cumulative <= 95:
                item["abc_class"] = "B"
            else:
                item["abc_class"] = "C"

        a_count = sum(1 for i in items if i["abc_class"] == "A")
        b_count = sum(1 for i in items if i["abc_class"] == "B")
        c_count = sum(1 for i in items if i["abc_class"] == "C")

        return {
            "items": items,
            "summary": {
                "period_days": days,
                "total_value_uzs": grand_total,
                "A_items": a_count,
                "B_items": b_count,
                "C_items": c_count,
                "A_pct_of_items": round(a_count / len(items) * 100, 1) if items else 0,
            }
        }

    @classmethod
    def _get_xyz_analysis(cls, days: int = 30) -> Dict:
        """XYZ Analysis: classify stock items by demand stability.
        Uses coefficient of variation (CV = stddev / mean) of weekly consumption.
        X = stable (CV < 0.5), Y = variable (0.5-1.0), Z = unpredictable (CV > 1.0)
        """
        cutoff = timezone.now().date() - timedelta(days=days)
        num_weeks = max(days // 7, 1)

        weekly_consumption = StockTransaction.objects.filter(
            movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
            created_at__date__gte=cutoff
        ).annotate(
            week=TruncWeek("created_at")
        ).values(
            "stock_item__id", "stock_item__name", "stock_item__sku",
            "stock_item__base_unit__short_name", "week"
        ).annotate(
            week_qty=Sum("base_quantity")
        ).order_by("stock_item__id", "week")

        item_weeks = {}
        for row in weekly_consumption:
            sid = row["stock_item__id"]
            if sid not in item_weeks:
                item_weeks[sid] = {
                    "id": sid,
                    "name": row["stock_item__name"],
                    "sku": row["stock_item__sku"],
                    "unit": row["stock_item__base_unit__short_name"],
                    "weekly_values": []
                }
            item_weeks[sid]["weekly_values"].append(abs(float(row["week_qty"] or 0)))

        items = []
        for sid, data in item_weeks.items():
            values = data["weekly_values"]
            while len(values) < num_weeks:
                values.append(0)

            mean = sum(values) / len(values) if values else 0
            if mean > 0 and len(values) > 1:
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                stddev = math.sqrt(variance)
                cv = stddev / mean
            else:
                cv = 0

            if cv < 0.5:
                xyz_class = "X"
            elif cv < 1.0:
                xyz_class = "Y"
            else:
                xyz_class = "Z"

            items.append({
                "id": data["id"],
                "name": data["name"],
                "sku": data["sku"],
                "unit": data["unit"],
                "weekly_avg": round(mean, 2),
                "weekly_stddev": round(stddev if mean > 0 else 0, 2),
                "cv": round(cv, 3),
                "xyz_class": xyz_class,
                "demand_pattern": {
                    "X": "Stable, predictable demand",
                    "Y": "Variable, somewhat predictable",
                    "Z": "Highly unpredictable demand"
                }[xyz_class]
            })

        items.sort(key=lambda x: x["cv"])

        return {
            "items": items,
            "summary": {
                "period_days": days,
                "weeks_analyzed": num_weeks,
                "X_items": sum(1 for i in items if i["xyz_class"] == "X"),
                "Y_items": sum(1 for i in items if i["xyz_class"] == "Y"),
                "Z_items": sum(1 for i in items if i["xyz_class"] == "Z"),
            }
        }

    @classmethod
    def _get_abc_xyz_matrix(cls, days: int = 30) -> Dict:
        """Combined ABC-XYZ matrix with strategy recommendations."""
        abc = cls._get_abc_analysis(days)
        xyz = cls._get_xyz_analysis(days)

        if not abc or not abc.get("items"):
            return {"matrix": {}, "items": []}

        abc_map = {i["id"]: i["abc_class"] for i in abc["items"]}
        xyz_map = {i["id"]: i for i in xyz.get("items", [])}

        strategies = {
            "AX": "High value, stable demand. Use JIT purchasing with tight reorder points. Monitor closely.",
            "AY": "High value, variable demand. Keep moderate safety stock. Forecast carefully.",
            "AZ": "High value, unpredictable. Maintain high safety stock. Review frequently.",
            "BX": "Medium value, stable. Automate reordering with standard quantities.",
            "BY": "Medium value, variable. Regular review cycle with flexible quantities.",
            "BZ": "Medium value, unpredictable. Higher safety stock, review sourcing.",
            "CX": "Low value, stable. Bulk order infrequently to minimize ordering cost.",
            "CY": "Low value, variable. Order as needed, minimal investment.",
            "CZ": "Low value, unpredictable. Consider discontinuing or keeping bare minimum.",
        }

        matrix = {k: [] for k in strategies}
        combined_items = []

        for item in abc["items"]:
            abc_class = item["abc_class"]
            xyz_data = xyz_map.get(item["id"])
            xyz_class = xyz_data["xyz_class"] if xyz_data else "Z"
            combo = f"{abc_class}{xyz_class}"

            entry = {
                "name": item["name"],
                "abc_class": abc_class,
                "xyz_class": xyz_class,
                "combined": combo,
                "consumption_value_uzs": item["total_value_uzs"],
                "pct_of_total": item["pct_of_total"],
                "cv": xyz_data["cv"] if xyz_data else None,
                "strategy": strategies.get(combo, "Review individually"),
            }
            matrix[combo].append(entry["name"])
            combined_items.append(entry)

        matrix_summary = {}
        for combo, names in matrix.items():
            if names:
                matrix_summary[combo] = {
                    "count": len(names),
                    "items": names[:10],
                    "strategy": strategies[combo]
                }

        return {
            "matrix": matrix_summary,
            "items": combined_items,
            "total_classified": len(combined_items),
        }

    @classmethod
    def _get_menu_engineering(cls, days: int = 30) -> Dict:
        """Menu Engineering (BCG-style matrix for menu items):
        Stars: high popularity + high margin
        Plow Horses: high popularity + low margin
        Puzzles: low popularity + high margin
        Dogs: low popularity + low margin
        """
        from stock.models import ProductStockLink, RecipeIngredient
        cutoff = timezone.now().date() - timedelta(days=days)

        product_sales = OrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=cutoff
        ).values(
            "product__id", "product__name", "product__price",
            "product__category__name"
        ).annotate(
            qty_sold=Sum("quantity"),
            revenue=Sum(F("quantity") * F("price"))
        ).order_by("-qty_sold")

        if not product_sales:
            return {"items": [], "summary": {}}

        items = []
        for ps in product_sales:
            pid = ps["product__id"]
            selling_price = float(ps["product__price"] or 0)
            qty = ps["qty_sold"] or 0
            revenue = float(ps["revenue"] or 0)

            ingredient_cost = 0
            link = ProductStockLink.objects.filter(
                product_id=pid, is_active=True
            ).select_related("recipe", "stock_item").first()

            if link:
                if link.link_type == "RECIPE" and link.recipe:
                    for ing in link.recipe.ingredients.select_related("stock_item"):
                        ingredient_cost += float(ing.stock_item.avg_cost_price * ing.quantity)
                elif link.link_type == "DIRECT_ITEM" and link.stock_item:
                    ingredient_cost = float(
                        link.stock_item.avg_cost_price * link.quantity_per_sale
                    )
                elif link.link_type == "COMPONENT_BASED":
                    for comp in link.components.filter(is_default=True).select_related("stock_item"):
                        ingredient_cost += float(
                            comp.stock_item.avg_cost_price * comp.quantity
                        )

            margin = selling_price - ingredient_cost
            margin_pct = (margin / selling_price * 100) if selling_price > 0 else 0

            items.append({
                "product_id": pid,
                "name": ps["product__name"],
                "category": ps["product__category__name"],
                "selling_price_uzs": selling_price,
                "ingredient_cost_uzs": round(ingredient_cost, 2),
                "margin_uzs": round(margin, 2),
                "margin_pct": round(margin_pct, 1),
                "qty_sold": qty,
                "revenue_uzs": revenue,
                "profit_uzs": round(margin * qty, 2),
            })

        if not items:
            return {"items": [], "summary": {}}

        avg_qty = sum(i["qty_sold"] for i in items) / len(items)
        avg_margin_pct = sum(i["margin_pct"] for i in items) / len(items)

        for item in items:
            high_pop = item["qty_sold"] >= avg_qty
            high_margin = item["margin_pct"] >= avg_margin_pct

            if high_pop and high_margin:
                item["category_me"] = "Star"
                item["action"] = "Protect and promote. Maintain quality and visibility."
            elif high_pop and not high_margin:
                item["category_me"] = "Plow Horse"
                item["action"] = "Increase price carefully or reduce ingredient cost."
            elif not high_pop and high_margin:
                item["category_me"] = "Puzzle"
                item["action"] = "Increase visibility. Promote more, reposition on menu."
            else:
                item["category_me"] = "Dog"
                item["action"] = "Consider removing or redesigning with cheaper ingredients."

        items.sort(key=lambda x: x["profit_uzs"], reverse=True)

        stars = [i for i in items if i["category_me"] == "Star"]
        plow_horses = [i for i in items if i["category_me"] == "Plow Horse"]
        puzzles = [i for i in items if i["category_me"] == "Puzzle"]
        dogs = [i for i in items if i["category_me"] == "Dog"]

        return {
            "items": items,
            "summary": {
                "period_days": days,
                "total_products": len(items),
                "avg_qty_threshold": round(avg_qty, 1),
                "avg_margin_pct_threshold": round(avg_margin_pct, 1),
                "stars": len(stars),
                "plow_horses": len(plow_horses),
                "puzzles": len(puzzles),
                "dogs": len(dogs),
                "total_profit_uzs": sum(i["profit_uzs"] for i in items),
                "star_names": [i["name"] for i in stars[:10]],
                "dog_names": [i["name"] for i in dogs[:10]],
            }
        }

    @classmethod
    def _get_profitability_analysis(cls, days: int = 30) -> Dict:
        """Per-product profitability: selling price vs COGS via recipes/stock links."""
        me = cls._get_menu_engineering(days)
        if not me or not me.get("items"):
            return {"products": [], "summary": {}}

        items = me["items"]
        total_revenue = sum(i["revenue_uzs"] for i in items)
        total_cogs = sum(i["ingredient_cost_uzs"] * i["qty_sold"] for i in items)
        total_profit = sum(i["profit_uzs"] for i in items)

        top_profit = sorted(items, key=lambda x: x["profit_uzs"], reverse=True)[:10]
        worst_margin = sorted(items, key=lambda x: x["margin_pct"])[:10]

        return {
            "products": [{
                "name": i["name"],
                "category": i["category"],
                "selling_price_uzs": i["selling_price_uzs"],
                "cost_uzs": i["ingredient_cost_uzs"],
                "margin_uzs": i["margin_uzs"],
                "margin_pct": i["margin_pct"],
                "qty_sold": i["qty_sold"],
                "total_profit_uzs": i["profit_uzs"],
            } for i in items],
            "top_profit_makers": [{"name": i["name"], "profit_uzs": i["profit_uzs"], "margin_pct": i["margin_pct"]} for i in top_profit],
            "worst_margins": [{"name": i["name"], "margin_pct": i["margin_pct"], "cost_uzs": i["ingredient_cost_uzs"]} for i in worst_margin],
            "summary": {
                "total_revenue_uzs": total_revenue,
                "total_cogs_uzs": total_cogs,
                "gross_profit_uzs": total_profit,
                "gross_margin_pct": round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
                "products_with_known_cost": sum(1 for i in items if i["ingredient_cost_uzs"] > 0),
                "products_without_cost": sum(1 for i in items if i["ingredient_cost_uzs"] == 0),
            }
        }

    @classmethod
    def _get_inventory_health(cls, days: int = 30) -> Dict:
        """Inventory health metrics: turnover, dead stock, carrying cost, days of supply."""
        cutoff = timezone.now().date() - timedelta(days=days)

        levels = StockLevel.objects.filter(
            stock_item__is_active=True
        ).select_related("stock_item", "stock_item__base_unit", "location")

        consumption = dict(
            StockTransaction.objects.filter(
                movement_type__in=["SALE_OUT", "PRODUCTION_OUT"],
                created_at__date__gte=cutoff
            ).values("stock_item_id").annotate(
                total=Sum("base_quantity")
            ).values_list("stock_item_id", "total")
        )

        last_movement = dict(
            StockTransaction.objects.values("stock_item_id").annotate(
                last=Max("created_at")
            ).values_list("stock_item_id", "last")
        )

        waste = dict(
            StockTransaction.objects.filter(
                movement_type__in=["WASTE", "SPOILAGE"],
                created_at__date__gte=cutoff
            ).values("stock_item_id").annotate(
                total=Sum("base_quantity"),
                cost=Sum("total_cost")
            ).values_list("stock_item_id", "cost")
        )

        now = timezone.now()
        items = []
        total_inventory_value = 0
        total_waste_cost = 0
        dead_stock = []
        slow_moving = []

        for level in levels:
            sid = level.stock_item_id
            qty = float(level.quantity)
            avg_cost = float(level.stock_item.avg_cost_price)
            value = qty * avg_cost
            total_inventory_value += value

            used = abs(float(consumption.get(sid, 0)))
            daily_usage = used / days if days > 0 else 0
            dos = int(qty / daily_usage) if daily_usage > 0 else 999

            if used > 0:
                turnover = used / qty if qty > 0 else float("inf")
            else:
                turnover = 0

            waste_cost = abs(float(waste.get(sid, 0)))
            total_waste_cost += waste_cost

            last_move = last_movement.get(sid)
            days_since_last = (now - last_move).days if last_move else 999

            entry = {
                "name": level.stock_item.name,
                "location": level.location.name,
                "quantity": qty,
                "unit": level.stock_item.base_unit.short_name,
                "value_uzs": round(value, 2),
                "daily_usage": round(daily_usage, 2),
                "days_of_supply": dos,
                "turnover_ratio": round(turnover, 2),
                "days_since_last_movement": days_since_last,
                "waste_cost_uzs": waste_cost,
            }
            items.append(entry)

            if days_since_last > 60:
                dead_stock.append(entry)
            elif days_since_last > 30:
                slow_moving.append(entry)

        items.sort(key=lambda x: x["turnover_ratio"], reverse=True)
        dead_stock.sort(key=lambda x: x["value_uzs"], reverse=True)

        return {
            "items": items[:50],
            "dead_stock": dead_stock[:20],
            "slow_moving": slow_moving[:20],
            "summary": {
                "total_inventory_value_uzs": round(total_inventory_value, 2),
                "total_waste_cost_uzs": round(total_waste_cost, 2),
                "waste_pct": round(total_waste_cost / total_inventory_value * 100, 2) if total_inventory_value > 0 else 0,
                "dead_stock_count": len(dead_stock),
                "dead_stock_value_uzs": round(sum(d["value_uzs"] for d in dead_stock), 2),
                "slow_moving_count": len(slow_moving),
                "avg_turnover_ratio": round(sum(i["turnover_ratio"] for i in items) / len(items), 2) if items else 0,
                "avg_days_of_supply": round(sum(min(i["days_of_supply"], 365) for i in items) / len(items), 0) if items else 0,
            }
        }

    @classmethod
    def _get_sales_velocity(cls, days: int = 30) -> Dict:
        """Sales velocity: per-product revenue trend over time."""
        cutoff = timezone.now().date() - timedelta(days=days)

        weekly = OrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=cutoff
        ).annotate(
            week=TruncWeek("order__created_at")
        ).values(
            "product__name", "week"
        ).annotate(
            qty=Sum("quantity"),
            revenue=Sum(F("quantity") * F("price"))
        ).order_by("product__name", "week")

        products = {}
        for row in weekly:
            name = row["product__name"]
            if name not in products:
                products[name] = {"name": name, "weeks": []}
            products[name]["weeks"].append({
                "week": row["week"].isoformat() if row["week"] else "",
                "qty": row["qty"],
                "revenue_uzs": float(row["revenue"] or 0),
            })

        velocity = []
        for name, data in products.items():
            weeks = data["weeks"]
            if len(weeks) >= 2:
                first_rev = weeks[0]["revenue_uzs"]
                last_rev = weeks[-1]["revenue_uzs"]
                growth = ((last_rev - first_rev) / first_rev * 100) if first_rev > 0 else 0
            else:
                growth = 0

            total_rev = sum(w["revenue_uzs"] for w in weeks)
            total_qty = sum(w["qty"] for w in weeks)

            velocity.append({
                "name": name,
                "total_revenue_uzs": total_rev,
                "total_qty": total_qty,
                "weeks_active": len(weeks),
                "avg_weekly_revenue_uzs": round(total_rev / len(weeks), 2) if weeks else 0,
                "growth_pct": round(growth, 1),
                "trend": "growing" if growth > 10 else ("declining" if growth < -10 else "stable"),
            })

        velocity.sort(key=lambda x: x["total_revenue_uzs"], reverse=True)

        growing = [v for v in velocity if v["trend"] == "growing"]
        declining = [v for v in velocity if v["trend"] == "declining"]

        return {
            "products": velocity[:30],
            "growing": [{"name": v["name"], "growth_pct": v["growth_pct"]} for v in growing[:10]],
            "declining": [{"name": v["name"], "growth_pct": v["growth_pct"]} for v in declining[:10]],
            "summary": {
                "total_products_analyzed": len(velocity),
                "growing_count": len(growing),
                "stable_count": len([v for v in velocity if v["trend"] == "stable"]),
                "declining_count": len(declining),
            }
        }

    @classmethod
    def _needs_analytics(cls, query: str) -> bool:
        """Check if the query needs business analytics data."""
        q = query.lower()
        analytics_keywords = [
            "abc", "xyz", "matrix", "analysis", "analiz", "аналитик", "анализ",
            "menu engineering", "star", "dog", "puzzle", "plow",
            "profitability", "profit", "margin", "rentabel", "рентабел", "маржа", "прибыл",
            "turnover", "dead stock", "health", "velocity", "trend", "growth",
            "recommend", "improve", "suggest", "advice", "strategy",
            "tavsiya", "yaxshila", "strategiya", "tahlil",
            "рекоменд", "улучш", "совет", "стратег",
            "бизнес", "business", "biznes",
            "waste", "потер", "isrof",
            "оборачиваемость", "оборот",
            "foyda", "zarar", "narx", "tannarx",
        ]
        return any(kw in q for kw in analytics_keywords)

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

            if cls._needs_analytics(query):
                combined_data["business_analytics"] = {
                    "abc_analysis": cls._get_abc_analysis(),
                    "xyz_analysis": cls._get_xyz_analysis(),
                    "abc_xyz_matrix": cls._get_abc_xyz_matrix(),
                    "menu_engineering": cls._get_menu_engineering(),
                    "profitability": cls._get_profitability_analysis(),
                    "inventory_health": cls._get_inventory_health(),
                    "sales_velocity": cls._get_sales_velocity(),
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
        if any(w in q for w in ["abc", "xyz", "matrix", "analysis", "analiz"]):
            return ["ABC-XYZ matrix", "Menu engineering", "Profitability analysis", "Inventory health"]
        if any(w in q for w in ["recommend", "improve", "strategy", "business"]):
            return ["ABC analysis", "Menu engineering", "Dead stock report", "Sales velocity"]
        if any(w in q for w in ["а", "е", "и", "о", "у", "ы", "э", "ю", "я"]):
            return ["ABC анализ", "Рентабельность меню", "Продажи за сегодня", "Рекомендации по бизнесу"]
        if any(w in q for w in ["qancha", "qoldi", "bor", "ombor", "sotuv", "tahlil"]):
            return ["ABC tahlil", "Menu tahlili", "Bugungi sotuvlar", "Biznes tavsiyalar"]
        return ["ABC-XYZ analysis", "Menu engineering", "Today's sales", "Business recommendations"]


__all__ = ['AIStockAssistant']
