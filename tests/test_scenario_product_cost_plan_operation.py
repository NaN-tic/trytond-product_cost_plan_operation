import unittest
from decimal import Decimal

from proteus import Model
from trytond.modules.company.tests.tools import create_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Install production Module
        config = activate_modules('product_cost_plan_operation')

        # Create company
        _ = create_company()

        # Configuration production location
        Location = Model.get('stock.location')
        warehouse, = Location.find([('code', '=', 'WH')])
        production_location, = Location.find([('code', '=', 'PROD')])
        warehouse.production_location = production_location
        warehouse.save()

        # Create a route with two operations on diferent work center
        ProductUom = Model.get('product.uom')
        Route = Model.get('production.route')
        OperationType = Model.get('production.operation.type')
        assembly = OperationType(name='Assembly')
        assembly.save()
        clean = OperationType(name='clean')
        clean.save()
        hour, = ProductUom.find([('name', '=', 'Hour')])
        unit, = ProductUom.find([('name', '=', 'Unit')])
        WorkCenter = Model.get('production.work_center')
        WorkCenterCategory = Model.get('production.work_center.category')
        category = WorkCenterCategory()
        category.name = 'Default Category'
        category.uom = hour
        category.cost_price = Decimal('25.0')
        category.save()
        workcenter1 = WorkCenter()
        workcenter1.name = 'Assembler Machine'
        workcenter1.type = 'machine'
        workcenter1.category = category
        workcenter1.uom = hour
        workcenter1.cost_price = Decimal('25.0')
        workcenter1.save()
        workcenter2 = WorkCenter()
        workcenter2.name = 'Cleaner Machine'
        workcenter2.category = category
        workcenter2.type = 'machine'
        workcenter2.uom = hour
        workcenter2.cost_price = Decimal('50.0')
        workcenter2.save()
        route = Route(name='default route')
        route.uom = unit
        route_operation = route.operations.new()
        route_operation.sequence = 1
        route_operation.operation_type = assembly
        route_operation.work_center_category = category
        route_operation.work_center = workcenter1
        route_operation.time = 5
        route_operation.time_uom = hour
        route_operation.quantity = 1
        route_operation.quantity_uom = unit
        route_operation = route.operations.new()
        route_operation.sequence = 2
        route_operation.operation_type = clean
        route_operation.work_center_category = category
        route_operation.work_center = workcenter2
        route_operation.time = 1
        route_operation.time_uom = hour
        route_operation.quantity = 1
        route_operation.quantity_uom = unit
        route.save()
        route.reload()
        self.assertEqual(len(route.operations), 2)

        # Create product
        ProductTemplate = Model.get('product.template')
        Product = Model.get('product.product')
        product = Product()
        template = ProductTemplate()
        template.name = 'product'
        template.producible = True
        template.default_uom = unit
        template.type = 'goods'
        template.list_price = Decimal(30)
        template.save()
        product, = template.products
        product.cost_price = Decimal(20)
        product.save()

        # Create Components
        component1 = Product()
        template1 = ProductTemplate()
        template1.name = 'component 1'
        template1.default_uom = unit
        template1.type = 'goods'
        template1.list_price = Decimal(5)
        template1.save()
        component1, = template1.products
        component1.cost_price = Decimal(1)
        component1.save()
        meter, = ProductUom.find([('name', '=', 'Meter')])
        centimeter, = ProductUom.find([('symbol', '=', 'cm')])
        component2 = Product()
        template2 = ProductTemplate()
        template2.name = 'component 2'
        template2.default_uom = meter
        template2.type = 'goods'
        template2.list_price = Decimal(7)
        template2.save()
        component2, = template2.products
        component2.cost_price = Decimal(5)
        component2.save()

        # Create Bill of Material
        BOM = Model.get('production.bom')
        BOMInput = Model.get('production.bom.input')
        BOMOutput = Model.get('production.bom.output')
        bom = BOM(name='product')
        input1 = BOMInput()
        input1 = bom.inputs.new()
        input1.product = component1
        input1.quantity = 5
        input2 = BOMInput()
        input2 = bom.inputs.new()
        input2.product = component2
        input2.quantity = 150
        input2.unit = centimeter
        output = BOMOutput()
        output = bom.outputs.new()
        output.product = product
        output.quantity = 1
        bom.save()
        ProductBom = Model.get('product.product-production.bom')
        product.boms.append(ProductBom(bom=bom))
        product.save()

        # Create an Inventory
        Inventory = Model.get('stock.inventory')
        InventoryLine = Model.get('stock.inventory.line')
        storage, = Location.find([
            ('code', '=', 'STO'),
        ])
        inventory = Inventory()
        inventory.location = storage
        inventory_line1 = InventoryLine()
        inventory.lines.append(inventory_line1)
        inventory_line1.product = component1
        inventory_line1.quantity = 10
        inventory_line2 = InventoryLine()
        inventory.lines.append(inventory_line2)
        inventory_line2.product = component2
        inventory_line2.quantity = 5
        inventory.save()
        Inventory.confirm([inventory.id], config.context)
        self.assertEqual(inventory.state, 'done')

        # Create a cost plan for product
        CostPlan = Model.get('product.cost.plan')
        plan = CostPlan()
        plan.product = product
        plan.route = route
        plan.quantity = 1
        plan.save()
        plan.click('compute')
        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(len(plan.products), 2)
        product_cost, operations_cost = plan.costs
        self.assertEqual(product_cost.cost, plan.products_cost)
        self.assertEqual(operations_cost.cost, plan.operations_cost)
        self.assertEqual(plan.operations_cost, Decimal('150.0000'))
        self.assertEqual(plan.cost_price,
                         plan.products_cost + plan.operations_cost)

        # Create a cost plan for 10 units
        CostPlan = Model.get('product.cost.plan')
        plan = CostPlan()
        plan.product = product
        plan.route = route
        plan.quantity = 10
        plan.click('compute')
        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(len(plan.products), 2)
        self.assertEqual(plan.operations_cost, Decimal('150.0000'))
        self.assertEqual(plan.cost_price,
                         plan.products_cost + plan.operations_cost)
