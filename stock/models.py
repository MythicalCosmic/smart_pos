from django.db import models


class StockLocation(models.Model):
    class StockLocationTypes(models.TextChoices):
        warehouse = "Warehouse", "WAREHOUSE"
        kitchen = "Kitchen", "KITCHEN"
        storage = "Storage", "STORAGE"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=70, choices=StockLocationTypes.choices)
    # parent_location = models.ForeignKey(StockLocation,)  #TO DO  (FK)
    is_default = models.BooleanField(default=False)
    is_production_area = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.CharField(max_length=20)


class StockUnit(models.Model):
    class StockUnitType(models.TextChoices):
        weight = "Weight", "WEIGHT"
        volume = "Volume", "VOLUME"
        count = "Count", "COUNT"
        lenght = "Lenght", "LENGHT"
        time = "Time", "TIME"
    name = models.CharField(max_length=40) #example: kg, pcs, L
    short_name = models.CharField(max_length=20) #example kg, pc
    unit_type = models.CharField(max_length=50)
    is_base_unit = models.BooleanField(default=True)
    # base_unit = models.ForeignKey() #TO DO (FK)
    # coversion_factor = models.CharField() #TO DO converstion factor 
    decimal_places = models.DecimalField(max_digits=8)
