
from tgext.ecommerce.lib.cart import CartManager
from tgext.ecommerce.lib.category import CategoryManager
from tgext.ecommerce.lib.order import OrderManager
from tgext.ecommerce.lib.payments import paypal, null_payment
from tgext.ecommerce.lib.product import ProductManager







class ShopManager(object):
    cart = CartManager()
    product = ProductManager()
    category = CategoryManager()
    order = OrderManager()


    def pay(self, cart, redirection_url, cancel_url, paymentService=None):
        if paymentService == 'paypal':
            return paypal.pay(cart, redirection_url, cancel_url)
        elif paymentService == None:
            return null_payment.pay(cart, redirection_url)

    def confirm(self, cart, redirection, data, paymentService=None):
        if paymentService == 'paypal':
            return paypal.confirm(cart, redirection, data)
        elif paymentService == None:
            return null_payment.confirm(redirection)

    def execute(self, cart, data, paymentService=None):
        if paymentService == 'paypal':
            return paypal.execute(cart, data)
        elif paymentService == None:
            return null_payment.execute()
