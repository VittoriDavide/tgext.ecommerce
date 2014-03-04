# coding=utf-8
from __future__ import unicode_literals
from functools import wraps
from tgext.ecommerce.lib.exceptions import CartLockedException
from tgext.ecommerce.lib.product import ProductManager
from tgext.ecommerce.lib.utils import NoDefault
from tgext.ecommerce.model import models, Setting


def check_cart_lock(f):
    @wraps(f)
    def wrapper(*args, **kw):
        locked = Setting.query.find({'setting': 'cart_locked'}).first()
        if locked is not None and locked.value:
            raise CartLockedException('The cart is locked')
        return f(*args, **kw)
    return wrapper


class CartManager(object):
    @classmethod
    @check_cart_lock
    def create_or_get(cls, user_id):  #create_or_get_cart
        cart = cls.get(user_id)
        if cart is None:
            cart = models.Cart(user_id=user_id)
            models.DBSession.flush()
        return cart

    @classmethod
    @check_cart_lock
    def get(cls, user_id):  #get_cart
        return models.Cart.query.find({'user_id': user_id}).first()

    @classmethod
    @check_cart_lock
    def update_item_qty(cls, cart, sku, qty): #update_cart_item_qty
        product_in_cart = cart.items.get(sku, {})
        already_bought = product_in_cart.get('qty', 0)
        delta_qty = qty - already_bought
        if delta_qty == 0:
            return cart
        product = ProductManager.get(sku=sku)
        ProductManager.buy(cart, product, ProductManager._config_idx(product, sku), delta_qty)
        return cart

    @classmethod
    @check_cart_lock
    def delete_item(cls, cart, sku):  #delete_from_cart
        return cls.update_item_qty(cart, sku, 0)

    @classmethod
    @check_cart_lock
    def update_order_info(cls, cart, payment=NoDefault, shipment_info=NoDefault, shipping_charges=NoDefault,
                          bill=NoDefault, bill_info=NoDefault, notes=NoDefault, **details):

        if payment is not NoDefault:
            for k, v in payment.iteritems():
                setattr(cart.order_info.payment, k, v)

        if shipment_info is not NoDefault:
            cart.order_info.shipment_info.update(shipment_info)

        if shipping_charges is not NoDefault:
            cart.order_info.shipping_charges = shipping_charges

        if bill is not NoDefault:
            cart.order_info.bill = bill

        if bill_info is not NoDefault:
            for k, v in bill_info.iteritems():
                setattr(cart.order_info.bill_info, k, v)
        if notes is not NoDefault:
            cart.order_info.notes = notes

        if details is not {}:
            for k, v in details.iteritems():
                setattr(cart.order_info.details, k, v)

