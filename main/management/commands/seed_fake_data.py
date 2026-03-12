"""
Seed the database with realistic fast-food restaurant data.
Creates products, categories, users, 100+ orders across different times,
and full stock data (items, batches, transactions, suppliers, recipes, etc.)
"""
import random
from decimal import Decimal
from datetime import timedelta, datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.db.models import Sum

from main.models import (
    User, Category, Product, Order, OrderItem,
    CashRegister, Inkassa, DeliveryPerson
)
from stock.models import (
    StockLocation, StockUnit, StockCategory, StockItem,
    StockLevel, StockBatch, StockTransaction,
    Supplier, SupplierStockItem,
    Recipe, RecipeIngredient, RecipeStep,
    VarianceReasonCode,
    ProductStockLink, StockSettings,
)


class Command(BaseCommand):
    help = 'Seed database with realistic fast-food restaurant data'

    def add_arguments(self, parser):
        parser.add_argument('--orders', type=int, default=150, help='Number of orders to create')
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')

    def handle(self, *args, **options):
        num_orders = options['orders']
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            self._clear_data()

        self.stdout.write('Seeding data...')
        self._create_units()
        self._create_locations()
        self._create_stock_categories()
        self._create_users()
        self._create_delivery_persons()
        self._create_categories_and_products()
        self._create_stock_items()
        self._create_suppliers()
        self._create_batches_and_levels()
        self._create_recipes()
        self._create_variance_codes()
        self._create_orders(num_orders)
        self._create_stock_transactions()
        self._create_product_stock_links()
        self._create_stock_settings()
        self._create_inkassa()
        self._create_cash_register()

        self.stdout.write(self.style.SUCCESS(f'Done! Created {num_orders} orders with full stock data.'))

    def _clear_data(self):
        from stock.models import (
            ProductionOrderStep, ProductionOrderOutput, ProductionOrderIngredient,
            ProductionOrder, RecipeByProduct, RecipeIngredientSubstitute,
            StockCountItem, StockCount, StockTransferItem, StockTransfer,
            ProductComponentStock, ProductStockLink,
            PurchaseReceivingItem, PurchaseReceiving, PurchaseOrderItem, PurchaseOrder,
        )
        # Clear in dependency order
        dep_models = [
            ProductionOrderStep, ProductionOrderOutput, ProductionOrderIngredient,
            ProductionOrder,
            StockCountItem, StockCount,
            StockTransferItem, StockTransfer,
            ProductComponentStock, ProductStockLink,
            PurchaseReceivingItem, PurchaseReceiving, PurchaseOrderItem, PurchaseOrder,
            Inkassa, OrderItem, Order, CashRegister,
            StockTransaction, StockBatch, StockLevel,
            RecipeByProduct, RecipeIngredientSubstitute, RecipeIngredient, RecipeStep, Recipe,
            SupplierStockItem, Supplier,
            StockItem, StockCategory, StockUnit, StockLocation,
            Product, Category, DeliveryPerson,
            VarianceReasonCode,
        ]
        for m in dep_models:
            m.objects.all().delete()
        User.objects.exclude(role='ADMIN').delete()

    # ── Units ──
    def _create_units(self):
        self.units = {}
        unit_data = [
            ('Gram', 'g', 'WEIGHT', True, None, 1),
            ('Kilogram', 'kg', 'WEIGHT', False, 'Gram', 1000),
            ('Milliliter', 'ml', 'VOLUME', True, None, 1),
            ('Liter', 'L', 'VOLUME', False, 'Milliliter', 1000),
            ('Piece', 'pcs', 'COUNT', True, None, 1),
            ('Dozen', 'dz', 'COUNT', False, 'Piece', 12),
            ('Box', 'box', 'COUNT', False, 'Piece', 1),
        ]
        for name, short, utype, is_base, base_name, factor in unit_data:
            base = self.units.get(base_name) if base_name else None
            obj, _ = StockUnit.objects.get_or_create(
                name=name, defaults={
                    'short_name': short, 'unit_type': utype,
                    'is_base_unit': is_base, 'base_unit': base,
                    'conversion_factor': factor,
                }
            )
            self.units[name] = obj
        self.stdout.write(f'  Units: {len(self.units)}')

    # ── Locations ──
    def _create_locations(self):
        self.locations = {}
        loc_data = [
            ('Main Warehouse', 'WAREHOUSE', True, False),
            ('Kitchen', 'KITCHEN', False, True),
            ('Bar', 'BAR', False, True),
            ('Cold Storage', 'STORAGE', False, False),
            ('Prep Area', 'PREP', False, True),
        ]
        for i, (name, ltype, default, prod) in enumerate(loc_data):
            obj, _ = StockLocation.objects.get_or_create(
                name=name, defaults={
                    'type': ltype, 'is_default': default,
                    'is_production_area': prod, 'sort_order': i,
                }
            )
            self.locations[name] = obj
        self.stdout.write(f'  Locations: {len(self.locations)}')

    # ── Stock Categories ──
    def _create_stock_categories(self):
        self.stock_cats = {}
        cat_data = [
            ('Meat & Poultry', 'RAW_MATERIAL'),
            ('Vegetables', 'RAW_MATERIAL'),
            ('Dairy & Eggs', 'RAW_MATERIAL'),
            ('Bread & Buns', 'RAW_MATERIAL'),
            ('Sauces & Condiments', 'RAW_MATERIAL'),
            ('Beverages', 'FINISHED_GOOD'),
            ('Dry Goods', 'RAW_MATERIAL'),
            ('Oils & Fats', 'RAW_MATERIAL'),
            ('Frozen Items', 'SEMI_FINISHED'),
            ('Packaging', 'PACKAGING'),
        ]
        for name, ctype in cat_data:
            obj, _ = StockCategory.objects.get_or_create(
                name=name, defaults={'type': ctype}
            )
            self.stock_cats[name] = obj
        self.stdout.write(f'  Stock categories: {len(self.stock_cats)}')

    # ── Users ──
    def _create_users(self):
        self.users = []
        self.cashiers = []
        admin, _ = User.objects.get_or_create(
            email='admin@smartpos.uz',
            defaults={
                'first_name': 'Admin', 'last_name': 'Boss',
                'password': make_password('admin123'),
                'role': 'ADMIN', 'status': 'ACTIVE',
            }
        )
        self.users.append(admin)

        cashier_names = [
            ('Aziz', 'Karimov'), ('Dilnoza', 'Rakhimova'),
            ('Sardor', 'Toshmatov'), ('Malika', 'Usmonova'),
            ('Jasur', 'Aliyev'),
        ]
        for first, last in cashier_names:
            email = f"{first.lower()}.{last.lower()}@smartpos.uz"
            user, _ = User.objects.get_or_create(
                email=email, defaults={
                    'first_name': first, 'last_name': last,
                    'password': make_password('cashier123'),
                    'role': 'CASHIER', 'status': 'ACTIVE',
                    'last_login_at': timezone.now() - timedelta(hours=random.randint(0, 48)),
                }
            )
            self.users.append(user)
            self.cashiers.append(user)

        for i in range(5):
            first = random.choice(['Nodir', 'Shaxlo', 'Bobur', 'Kamola', 'Otabek'])
            last = random.choice(['Ergashev', 'Nazarova', 'Mirzayev', 'Saidova', 'Kholmatov'])
            email = f"user{i+1}@smartpos.uz"
            user, _ = User.objects.get_or_create(
                email=email, defaults={
                    'first_name': first, 'last_name': last,
                    'password': make_password('user123'),
                    'role': 'USER', 'status': 'ACTIVE',
                }
            )
            self.users.append(user)
        self.stdout.write(f'  Users: {len(self.users)}')

    # ── Delivery Persons ──
    def _create_delivery_persons(self):
        self.drivers = []
        names = [
            ('Bekzod', 'Juraev', '+998901234567'),
            ('Ulugbek', 'Normatov', '+998901234568'),
            ('Asilbek', 'Rajabov', '+998901234569'),
        ]
        for first, last, phone in names:
            d, _ = DeliveryPerson.objects.get_or_create(
                phone_number=phone, defaults={
                    'first_name': first, 'last_name': last, 'is_active': True,
                }
            )
            self.drivers.append(d)

    # ── POS Categories & Products ──
    def _create_categories_and_products(self):
        self.products = []
        menu = {
            ('Burgers', '#e74c3c,#c0392b', 'Classic burgers and sandwiches'): [
                ('Classic Burger', 28000), ('Cheeseburger', 32000), ('Double Burger', 45000),
                ('Chicken Burger', 35000), ('Spicy Burger', 38000), ('BBQ Burger', 42000),
                ('Veggie Burger', 25000), ('Fish Burger', 36000),
            ],
            ('Hot Dogs', '#f39c12,#e67e22', 'Hot dogs and sausages'): [
                ('Classic Hot Dog', 18000), ('Cheese Hot Dog', 22000),
                ('Chili Dog', 25000), ('Jumbo Hot Dog', 28000),
            ],
            ('Chicken', '#e67e22,#d35400', 'Fried and grilled chicken'): [
                ('Fried Chicken (3pc)', 35000), ('Fried Chicken (6pc)', 58000),
                ('Chicken Wings (8pc)', 42000), ('Chicken Nuggets (9pc)', 28000),
                ('Grilled Chicken', 38000), ('Chicken Strips', 30000),
            ],
            ('Combo Meals', '#9b59b6,#8e44ad', 'Value combo meals'): [
                ('Burger Combo', 45000), ('Chicken Combo', 52000),
                ('Family Combo', 120000), ('Kids Combo', 25000),
                ('Double Combo', 65000),
            ],
            ('Sides', '#2ecc71,#27ae60', 'Side dishes'): [
                ('French Fries (S)', 12000), ('French Fries (L)', 18000),
                ('Onion Rings', 15000), ('Coleslaw', 8000),
                ('Mozzarella Sticks', 20000), ('Corn on the Cob', 10000),
            ],
            ('Drinks', '#3498db,#2980b9', 'Beverages'): [
                ('Coca-Cola (0.5L)', 8000), ('Fanta (0.5L)', 8000),
                ('Sprite (0.5L)', 8000), ('Mineral Water', 5000),
                ('Fresh Juice', 15000), ('Milkshake', 22000),
                ('Iced Tea', 12000), ('Coffee', 14000),
            ],
            ('Desserts', '#e91e63,#c2185b', 'Sweet treats'): [
                ('Ice Cream (1 scoop)', 10000), ('Ice Cream (3 scoops)', 22000),
                ('Apple Pie', 15000), ('Brownie', 18000),
                ('Donut', 8000), ('Cheesecake', 25000),
            ],
            ('Wraps & Rolls', '#ff9800,#f57c00', 'Wraps and shawarma'): [
                ('Chicken Shawarma', 25000), ('Beef Shawarma', 30000),
                ('Chicken Wrap', 22000), ('Veggie Wrap', 18000),
            ],
        }

        for i, ((cat_name, colors_str, desc), items) in enumerate(menu.items()):
            from django.utils.text import slugify
            slug = slugify(cat_name, allow_unicode=True) or f'cat-{i}'
            cat, _ = Category.objects.get_or_create(
                slug=slug, defaults={
                    'name': cat_name,
                    'colors': [c.strip() for c in colors_str.split(',')],
                    'status': 'ACTIVE', 'sort_order': i,
                    'description': desc,
                }
            )
            for prod_name, price in items:
                prod, _ = Product.objects.get_or_create(
                    name=prod_name, category=cat, defaults={
                        'price': Decimal(str(price)),
                        'colors': cat.colors,
                    }
                )
                self.products.append(prod)
        self.stdout.write(f'  Products: {len(self.products)}')

    # ── Stock Items ──
    def _create_stock_items(self):
        self.stock_items = {}
        items = [
            # Meat
            ('Beef Patty', 'MEAT-001', 'Meat & Poultry', 'Gram', 'RAW', 5000, 20000, 8000, 3500, True),
            ('Chicken Breast', 'MEAT-002', 'Meat & Poultry', 'Gram', 'RAW', 3000, 15000, 5000, 4200, True),
            ('Chicken Wings', 'MEAT-003', 'Meat & Poultry', 'Gram', 'RAW', 2000, 10000, 4000, 3800, True),
            ('Beef Sausage', 'MEAT-004', 'Meat & Poultry', 'Piece', 'SEMI', 20, 200, 50, 2500, True),
            ('Chicken Nuggets (frozen)', 'MEAT-005', 'Frozen Items', 'Piece', 'SEMI', 50, 500, 100, 800, True),
            # Veggies
            ('Tomato', 'VEG-001', 'Vegetables', 'Gram', 'RAW', 2000, 10000, 4000, 800, True),
            ('Lettuce', 'VEG-002', 'Vegetables', 'Gram', 'RAW', 1000, 5000, 2000, 600, True),
            ('Onion', 'VEG-003', 'Vegetables', 'Gram', 'RAW', 2000, 10000, 3000, 400, True),
            ('Pickle', 'VEG-004', 'Vegetables', 'Gram', 'RAW', 1000, 5000, 2000, 500, True),
            ('Jalapeno', 'VEG-005', 'Vegetables', 'Gram', 'RAW', 500, 3000, 1000, 1200, True),
            ('Corn', 'VEG-006', 'Vegetables', 'Piece', 'RAW', 10, 100, 30, 3000, False),
            # Dairy
            ('Cheddar Cheese', 'DAI-001', 'Dairy & Eggs', 'Gram', 'RAW', 1000, 5000, 2000, 6000, True),
            ('Mozzarella', 'DAI-002', 'Dairy & Eggs', 'Gram', 'RAW', 500, 3000, 1000, 7000, True),
            ('Eggs', 'DAI-003', 'Dairy & Eggs', 'Piece', 'RAW', 20, 200, 60, 800, True),
            ('Butter', 'DAI-004', 'Dairy & Eggs', 'Gram', 'RAW', 500, 5000, 1000, 5500, True),
            ('Milk', 'DAI-005', 'Dairy & Eggs', 'Milliliter', 'RAW', 2000, 20000, 5000, 3, True),
            # Bread
            ('Burger Bun', 'BRD-001', 'Bread & Buns', 'Piece', 'SEMI', 30, 300, 80, 1500, False),
            ('Hot Dog Bun', 'BRD-002', 'Bread & Buns', 'Piece', 'SEMI', 20, 200, 50, 1200, False),
            ('Tortilla Wrap', 'BRD-003', 'Bread & Buns', 'Piece', 'SEMI', 20, 200, 50, 2000, False),
            # Sauces
            ('Ketchup', 'SAU-001', 'Sauces & Condiments', 'Gram', 'RAW', 1000, 10000, 3000, 300, False),
            ('Mustard', 'SAU-002', 'Sauces & Condiments', 'Gram', 'RAW', 500, 5000, 1500, 400, False),
            ('Mayonnaise', 'SAU-003', 'Sauces & Condiments', 'Gram', 'RAW', 1000, 10000, 3000, 350, False),
            ('BBQ Sauce', 'SAU-004', 'Sauces & Condiments', 'Gram', 'RAW', 500, 5000, 1500, 500, False),
            ('Chili Sauce', 'SAU-005', 'Sauces & Condiments', 'Gram', 'RAW', 300, 3000, 1000, 600, False),
            # Beverages
            ('Coca-Cola Syrup', 'BEV-001', 'Beverages', 'Milliliter', 'RAW', 5000, 50000, 10000, 5, False),
            ('Orange Juice', 'BEV-002', 'Beverages', 'Milliliter', 'RAW', 3000, 20000, 5000, 8, True),
            ('Ice Cream Base', 'BEV-003', 'Beverages', 'Milliliter', 'SEMI', 2000, 10000, 4000, 12, True),
            # Dry
            ('Flour', 'DRY-001', 'Dry Goods', 'Gram', 'RAW', 5000, 50000, 10000, 500, False),
            ('Cooking Oil', 'OIL-001', 'Oils & Fats', 'Milliliter', 'RAW', 5000, 50000, 10000, 4, False),
            ('French Fries (frozen)', 'FRZ-001', 'Frozen Items', 'Gram', 'SEMI', 5000, 30000, 10000, 1200, True),
            # Packaging
            ('Burger Box', 'PKG-001', 'Packaging', 'Piece', 'PACKAGING', 50, 1000, 200, 500, False),
            ('Paper Bag', 'PKG-002', 'Packaging', 'Piece', 'PACKAGING', 100, 2000, 300, 200, False),
            ('Drink Cup (0.5L)', 'PKG-003', 'Packaging', 'Piece', 'PACKAGING', 50, 1000, 200, 300, False),
        ]

        for name, sku, cat_name, unit_name, itype, reorder, max_stock, min_stock, cost, track_exp in items:
            obj, _ = StockItem.objects.get_or_create(
                sku=sku, defaults={
                    'name': name,
                    'category': self.stock_cats[cat_name],
                    'base_unit': self.units[unit_name],
                    'item_type': itype,
                    'reorder_point': Decimal(str(reorder)),
                    'max_stock_level': Decimal(str(max_stock)),
                    'min_stock_level': Decimal(str(min_stock)),
                    'cost_price': Decimal(str(cost)),
                    'avg_cost_price': Decimal(str(cost)),
                    'last_cost_price': Decimal(str(cost)),
                    'is_purchasable': True,
                    'track_expiry': track_exp,
                    'track_batches': True,
                    'default_expiry_days': 14 if track_exp else None,
                }
            )
            self.stock_items[name] = obj
        self.stdout.write(f'  Stock items: {len(self.stock_items)}')

    # ── Suppliers ──
    def _create_suppliers(self):
        self.suppliers = []
        suppliers_data = [
            ('Tashkent Meat Co.', 'Rustam Kholikov', '+998712345678', 'Tashkent', 2, 4),
            ('Fresh Farm Vegetables', 'Dilshod Ibragimov', '+998712345679', 'Tashkent', 1, 5),
            ('Uzbek Dairy Ltd.', 'Kamola Nurmatova', '+998712345680', 'Samarkand', 3, 4),
            ('Central Bakery', 'Anvar Sobirov', '+998712345681', 'Tashkent', 1, 5),
            ('Sauce Masters', 'Javlon Tursunov', '+998712345682', 'Tashkent', 5, 3),
            ('PackPro Uzbekistan', 'Shahlo Azimova', '+998712345683', 'Tashkent', 7, 4),
        ]
        for name, contact, phone, city, lead, rating in suppliers_data:
            s, _ = Supplier.objects.get_or_create(
                name=name, defaults={
                    'contact_person': contact, 'phone': phone, 'city': city,
                    'country': 'Uzbekistan', 'lead_time_days': lead,
                    'rating': rating, 'payment_terms_days': 15, 'currency': 'UZS',
                }
            )
            self.suppliers.append(s)

            # Link some stock items
            category_map = {
                'Tashkent Meat Co.': 'Meat & Poultry',
                'Fresh Farm Vegetables': 'Vegetables',
                'Uzbek Dairy Ltd.': 'Dairy & Eggs',
                'Central Bakery': 'Bread & Buns',
                'Sauce Masters': 'Sauces & Condiments',
                'PackPro Uzbekistan': 'Packaging',
            }
            cat_name = category_map.get(name)
            if cat_name:
                for si_name, si_obj in self.stock_items.items():
                    if si_obj.category and si_obj.category.name == cat_name:
                        SupplierStockItem.objects.get_or_create(
                            supplier=s, stock_item=si_obj, defaults={
                                'unit': si_obj.base_unit,
                                'price': si_obj.cost_price * Decimal('1.1'),
                                'is_preferred': True,
                            }
                        )
        self.stdout.write(f'  Suppliers: {len(self.suppliers)}')

    # ── Batches & Stock Levels ──
    def _create_batches_and_levels(self):
        today = timezone.now().date()
        batch_count = 0
        for name, item in self.stock_items.items():
            locations_to_stock = ['Main Warehouse']
            if item.category and item.category.name in ['Meat & Poultry', 'Vegetables', 'Dairy & Eggs', 'Sauces & Condiments']:
                locations_to_stock.append('Kitchen')
            if item.category and item.category.name == 'Beverages':
                locations_to_stock.append('Bar')

            for loc_name in locations_to_stock:
                loc = self.locations[loc_name]
                qty = Decimal(str(random.randint(
                    int(item.reorder_point * Decimal('0.5')),
                    int(item.max_stock_level or item.reorder_point * 3)
                )))

                StockLevel.objects.update_or_create(
                    stock_item=item, location=loc,
                    defaults={'quantity': qty, 'last_restocked_at': timezone.now()}
                )

                # Create 1-3 batches per location
                remaining = qty
                for b in range(random.randint(1, 3)):
                    if remaining <= 0:
                        break
                    batch_qty = remaining if b == 2 else Decimal(str(random.randint(1, int(remaining))))
                    remaining -= batch_qty
                    exp_date = today + timedelta(days=random.randint(-5, 45)) if item.track_expiry else None
                    batch_num = f"B-{item.sku}-{loc_name[:3].upper()}-{b+1:03d}"

                    StockBatch.objects.get_or_create(
                        batch_number=batch_num, stock_item=item, defaults={
                            'location': loc,
                            'initial_quantity': batch_qty,
                            'current_quantity': batch_qty,
                            'unit_cost': item.cost_price,
                            'total_cost': batch_qty * item.cost_price,
                            'manufactured_date': today - timedelta(days=random.randint(1, 30)),
                            'expiry_date': exp_date,
                            'status': 'EXPIRED' if exp_date and exp_date < today else 'AVAILABLE',
                            'supplier': random.choice(self.suppliers) if self.suppliers else None,
                        }
                    )
                    batch_count += 1
        self.stdout.write(f'  Batches: {batch_count}')

    # ── Recipes ──
    def _create_recipes(self):
        g = self.units['Gram']
        ml = self.units['Milliliter']
        pcs = self.units['Piece']

        recipes_data = [
            ('Classic Burger', 'RCP-001', 'PRODUCTION', 'Burger Bun', 1, pcs, [
                ('Beef Patty', 150, g), ('Burger Bun', 1, pcs), ('Lettuce', 30, g),
                ('Tomato', 40, g), ('Onion', 20, g), ('Ketchup', 15, g),
                ('Cheddar Cheese', 30, g),
            ]),
            ('Chicken Shawarma', 'RCP-002', 'PRODUCTION', 'Tortilla Wrap', 1, pcs, [
                ('Chicken Breast', 180, g), ('Tortilla Wrap', 1, pcs), ('Tomato', 50, g),
                ('Onion', 30, g), ('Mayonnaise', 20, g), ('Chili Sauce', 10, g),
            ]),
            ('French Fries (Large)', 'RCP-003', 'PREPARATION', 'French Fries (frozen)', 250, g, [
                ('French Fries (frozen)', 250, g), ('Cooking Oil', 100, ml),
            ]),
            ('Milkshake', 'RCP-004', 'PRODUCTION', 'Ice Cream Base', 350, ml, [
                ('Ice Cream Base', 150, ml), ('Milk', 200, ml),
            ]),
        ]

        for rname, code, rtype, output_name, out_qty, out_unit, ingredients in recipes_data:
            output_item = self.stock_items.get(output_name)
            if not output_item:
                continue
            recipe, created = Recipe.objects.get_or_create(
                code=code, defaults={
                    'name': rname, 'recipe_type': rtype,
                    'output_item': output_item, 'output_quantity': Decimal(str(out_qty)),
                    'output_unit': out_unit, 'estimated_time_minutes': random.randint(3, 15),
                    'difficulty_level': random.randint(1, 3),
                    'production_location': self.locations['Kitchen'],
                }
            )
            if created:
                for idx, (ing_name, qty, unit) in enumerate(ingredients):
                    si = self.stock_items.get(ing_name)
                    if si:
                        RecipeIngredient.objects.create(
                            recipe=recipe, stock_item=si,
                            quantity=Decimal(str(qty)), unit=unit, sort_order=idx,
                        )
                RecipeStep.objects.create(recipe=recipe, step_number=1, title='Prepare ingredients', duration_minutes=2)
                RecipeStep.objects.create(recipe=recipe, step_number=2, title='Cook / Assemble', duration_minutes=5)
                RecipeStep.objects.create(recipe=recipe, step_number=3, title='Plate and serve', duration_minutes=1)
        self.stdout.write(f'  Recipes: {Recipe.objects.count()}')

    # ── Variance Codes ──
    def _create_variance_codes(self):
        codes = [
            ('DAMAGE', 'Damaged Goods', False),
            ('THEFT', 'Theft / Shrinkage', True),
            ('SPOIL', 'Spoilage', False),
            ('MISCOUNT', 'Counting Error', False),
            ('SAMPLE', 'Staff Meal / Sample', False),
        ]
        for code, name, approval in codes:
            VarianceReasonCode.objects.get_or_create(
                code=code, defaults={'name': name, 'requires_approval': approval}
            )

    # ── Orders (the big one) ──
    def _create_orders(self, num_orders):
        now = timezone.now()
        order_count = 0
        display_counter = 1

        for i in range(num_orders):
            # Spread orders across last 30 days with more recent ones
            days_ago = random.randint(60, 120)

            hour = random.choices(
                range(24),
                weights=[0,0,0,0,0,0,0,1,3,5,8,10,12,10,8,6,5,7,9,11,8,5,2,1]
            )[0]

            minute = random.randint(0, 59)

            order_time = (now - timedelta(days=days_ago)).replace(
                hour=hour,
                minute=minute,
                second=random.randint(0, 59),
                microsecond=0
            )

            cashier = random.choice(self.cashiers) if self.cashiers else self.users[0]
            customer = random.choice(self.users)
            order_type = random.choices(
                ['HALL', 'DELIVERY', 'PICKUP'], weights=[60, 25, 15]
            )[0]
            status = random.choices(
                ['COMPLETED', 'COMPLETED', 'COMPLETED', 'COMPLETED',
                 'CANCELED', 'OPEN', 'PREPARING', 'READY'],
                weights=[50, 20, 10, 5, 5, 4, 3, 3]
            )[0]
            is_paid = status == 'COMPLETED' or (status != 'CANCELED' and random.random() > 0.3)

            delivery_person = random.choice(self.drivers) if order_type == 'DELIVERY' else None

            order = Order(
                user=customer, cashier=cashier,
                display_id=display_counter,
                order_type=order_type, status=status,
                is_paid=is_paid,
                delivery_person=delivery_person,
                total_amount=0,
            )
            # Override auto_now_add
            order.save()
            Order.objects.filter(pk=order.pk).update(created_at=order_time)

            if status == 'COMPLETED':
                ready_time = order_time + timedelta(minutes=random.randint(5, 25))
                paid_time = ready_time + timedelta(minutes=random.randint(0, 10))
                Order.objects.filter(pk=order.pk).update(ready_at=ready_time, paid_at=paid_time)

            # Add 1-6 items per order
            num_items = random.choices([1, 2, 3, 4, 5, 6], weights=[15, 30, 25, 15, 10, 5])[0]
            chosen_products = random.sample(self.products, min(num_items, len(self.products)))
            total = Decimal('0')

            for product in chosen_products:
                qty = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
                item_price = product.price
                OrderItem.objects.create(
                    order=order, product=product,
                    quantity=qty, price=item_price,
                    ready_at=order_time + timedelta(minutes=random.randint(5, 20)) if status in ['READY', 'COMPLETED'] else None,
                )
                total += item_price * qty

            Order.objects.filter(pk=order.pk).update(total_amount=total, updated_at=order_time)
            display_counter = (display_counter % 100) + 1
            order_count += 1

        self.stdout.write(f'  Orders: {order_count}')

    # ── Stock Transactions ──
    def _create_stock_transactions(self):
        from django.contrib.auth.models import User as AuthUser
        today = timezone.now().date()
        # StockTransaction.user FK points to auth.User, not main.User
        auth_admin = AuthUser.objects.filter(is_superuser=True).first()
        if not auth_admin:
            auth_admin = AuthUser.objects.create_superuser('admin', 'admin@smartpos.uz', 'admin123')
        txn_count = 0
        warehouse = self.locations['Main Warehouse']

        for name, item in self.stock_items.items():
            # Opening balance
            level = StockLevel.objects.filter(stock_item=item, location=warehouse).first()
            if not level:
                continue
            txn_num = f"TXN-OB-{item.sku}"
            StockTransaction.objects.get_or_create(
                transaction_number=txn_num, defaults={
                    'stock_item': item, 'location': warehouse,
                    'movement_type': 'OPENING_BALANCE',
                    'quantity': level.quantity, 'unit': item.base_unit,
                    'base_quantity': level.quantity,
                    'quantity_before': 0, 'quantity_after': level.quantity,
                    'unit_cost': item.cost_price,
                    'total_cost': level.quantity * item.cost_price,
                    'user': auth_admin,
                }
            )
            txn_count += 1

            # Some sale transactions over last 30 days
            for d in range(30):
                if random.random() > 0.4:
                    continue
                sale_qty = Decimal(str(random.randint(1, max(1, int(item.reorder_point * Decimal('0.1'))))))
                txn_num = f"TXN-SALE-{item.sku}-D{d}"
                StockTransaction.objects.get_or_create(
                    transaction_number=txn_num, defaults={
                        'stock_item': item, 'location': warehouse,
                        'movement_type': 'SALE_OUT',
                        'quantity': sale_qty, 'unit': item.base_unit,
                        'base_quantity': -sale_qty,
                        'quantity_before': level.quantity,
                        'quantity_after': level.quantity - sale_qty,
                        'unit_cost': item.cost_price,
                        'total_cost': sale_qty * item.cost_price,
                        'user': auth_admin,
                    }
                )
                txn_count += 1
        self.stdout.write(f'  Transactions: {txn_count}')

    # ── Product-Stock Links ──
    def _create_product_stock_links(self):
        products_by_name = {p.name: p for p in self.products}
        recipes_by_code = {r.code: r for r in Recipe.objects.all()}
        link_count = 0

        # (product_name, link_type, recipe_code_or_None, stock_item_name_or_None, qty, unit_name)
        links_data = [
            # Burgers
            ('Classic Burger', 'RECIPE', 'RCP-001', None, 1, 'Piece'),
            ('Cheeseburger', 'DIRECT_ITEM', None, 'Beef Patty', 180, 'Gram'),
            ('Double Burger', 'DIRECT_ITEM', None, 'Beef Patty', 300, 'Gram'),
            ('Chicken Burger', 'DIRECT_ITEM', None, 'Chicken Breast', 180, 'Gram'),
            ('Spicy Burger', 'DIRECT_ITEM', None, 'Beef Patty', 150, 'Gram'),
            ('BBQ Burger', 'DIRECT_ITEM', None, 'Beef Patty', 150, 'Gram'),
            ('Veggie Burger', 'DIRECT_ITEM', None, 'Burger Bun', 1, 'Piece'),
            ('Fish Burger', 'DIRECT_ITEM', None, 'Burger Bun', 1, 'Piece'),
            # Hot Dogs
            ('Classic Hot Dog', 'DIRECT_ITEM', None, 'Beef Sausage', 1, 'Piece'),
            ('Cheese Hot Dog', 'DIRECT_ITEM', None, 'Beef Sausage', 1, 'Piece'),
            ('Chili Dog', 'DIRECT_ITEM', None, 'Beef Sausage', 1, 'Piece'),
            ('Jumbo Hot Dog', 'DIRECT_ITEM', None, 'Beef Sausage', 2, 'Piece'),
            # Chicken
            ('Fried Chicken (3pc)', 'DIRECT_ITEM', None, 'Chicken Breast', 450, 'Gram'),
            ('Fried Chicken (6pc)', 'DIRECT_ITEM', None, 'Chicken Breast', 900, 'Gram'),
            ('Chicken Wings (8pc)', 'DIRECT_ITEM', None, 'Chicken Wings', 400, 'Gram'),
            ('Chicken Nuggets (9pc)', 'DIRECT_ITEM', None, 'Chicken Nuggets (frozen)', 9, 'Piece'),
            ('Grilled Chicken', 'DIRECT_ITEM', None, 'Chicken Breast', 300, 'Gram'),
            ('Chicken Strips', 'DIRECT_ITEM', None, 'Chicken Breast', 250, 'Gram'),
            # Sides
            ('French Fries (S)', 'DIRECT_ITEM', None, 'French Fries (frozen)', 150, 'Gram'),
            ('French Fries (L)', 'DIRECT_ITEM', None, 'French Fries (frozen)', 250, 'Gram'),
            ('Onion Rings', 'DIRECT_ITEM', None, 'Onion', 100, 'Gram'),
            ('Mozzarella Sticks', 'DIRECT_ITEM', None, 'Mozzarella', 80, 'Gram'),
            ('Corn on the Cob', 'DIRECT_ITEM', None, 'Corn', 1, 'Piece'),
            # Drinks
            ('Coca-Cola (0.5L)', 'DIRECT_ITEM', None, 'Coca-Cola Syrup', 50, 'Milliliter'),
            ('Fresh Juice', 'DIRECT_ITEM', None, 'Orange Juice', 300, 'Milliliter'),
            ('Milkshake', 'RECIPE', 'RCP-004', None, 1, 'Piece'),
            # Desserts
            ('Ice Cream (1 scoop)', 'DIRECT_ITEM', None, 'Ice Cream Base', 100, 'Milliliter'),
            ('Ice Cream (3 scoops)', 'DIRECT_ITEM', None, 'Ice Cream Base', 300, 'Milliliter'),
            # Wraps
            ('Chicken Shawarma', 'RECIPE', 'RCP-002', None, 1, 'Piece'),
            ('Beef Shawarma', 'DIRECT_ITEM', None, 'Beef Patty', 180, 'Gram'),
            ('Chicken Wrap', 'DIRECT_ITEM', None, 'Chicken Breast', 150, 'Gram'),
            ('Veggie Wrap', 'DIRECT_ITEM', None, 'Tortilla Wrap', 1, 'Piece'),
        ]

        for prod_name, link_type, recipe_code, si_name, qty, unit_name in links_data:
            product = products_by_name.get(prod_name)
            if not product:
                continue

            defaults = {
                'link_type': link_type,
                'quantity_per_sale': Decimal(str(qty)),
                'unit': self.units.get(unit_name),
                'deduct_on_status': 'PREPARING',
                'is_active': True,
            }

            if link_type == 'RECIPE' and recipe_code:
                recipe = recipes_by_code.get(recipe_code)
                if not recipe:
                    continue
                defaults['recipe'] = recipe
            elif link_type == 'DIRECT_ITEM' and si_name:
                si = self.stock_items.get(si_name)
                if not si:
                    continue
                defaults['stock_item'] = si

            _, created = ProductStockLink.objects.get_or_create(
                product=product, defaults=defaults
            )
            if created:
                link_count += 1

        self.stdout.write(f'  Product-Stock links: {link_count}')

    # ── Stock Settings ──
    def _create_stock_settings(self):
        settings = StockSettings.load()
        settings.stock_enabled = True
        settings.auto_deduct_on_sale = True
        settings.deduct_on_order_status = 'PREPARING'
        settings.allow_negative_stock = True
        settings.track_cost = True
        settings.track_batches = True
        settings.low_stock_alert_enabled = True
        settings.default_location = self.locations.get('Main Warehouse')
        settings.save()
        self.stdout.write(f'  Stock settings: enabled={settings.stock_enabled}, auto_deduct={settings.auto_deduct_on_sale}')

    # ── Inkassa ──
    def _create_inkassa(self):
        now = timezone.now()
        for cashier in self.cashiers:
            cashier_orders = Order.objects.filter(cashier=cashier, is_paid=True, is_deleted=False)
            total_rev = cashier_orders.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
            count = cashier_orders.count()
            if total_rev > 0:
                Inkassa.objects.get_or_create(
                    cashier=cashier, amount=total_rev,
                    defaults={
                        'inkass_type': random.choice(['CASH', 'UZCARD', 'HUMO']),
                        'balance_before': total_rev,
                        'balance_after': 0,
                        'total_orders': count,
                        'total_revenue': total_rev,
                        'period_start': now - timedelta(hours=8),
                    }
                )
        self.stdout.write(f'  Inkassa records: {Inkassa.objects.count()}')

    # ── Cash Register ──
    def _create_cash_register(self):
        total = Order.objects.filter(
            is_paid=True, is_deleted=False
        ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
        inkassa_total = Inkassa.objects.filter(is_deleted=False).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        balance = total - inkassa_total
        CashRegister.objects.update_or_create(
            pk=1, defaults={'current_balance': max(balance, Decimal('0'))}
        )
        self.stdout.write(f'  Cash register balance: {balance:,.0f} UZS')
