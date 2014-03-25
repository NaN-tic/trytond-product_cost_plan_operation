#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .plan import *


def register():
    Pool.register(
        PlanOperationLine,
        Plan,
        CreateRouteStart,
        module='product_cost_plan_operation', type_='model')
    Pool.register(
        CreateRoute,
        module='product_cost_plan_operation', type_='wizard')
