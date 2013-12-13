from tgextecommerce.lib.exceptions import AlreadyExistingSlugException, AlreadyExistingSkuException
from tgextecommerce.lib.utils import slugify
from bson import ObjectId
from ming.odm import mapper

class Models(object):
    def __init__(self):
        self._models = None

    @property
    def models(self):
        if self._models is None:
            from tgextecommerce.model import models
            self._models = models
        return self._models

    def __getattr__(self, item):
        return getattr(self.models, item)

models = Models()


class ShopManager(object):
    def create_product(self, type, sku, name, description='', price=1.0,
                       vat=0.0, qty=0, initial_quantity=0,
                       variety=None, active=True, valid_from=None, valid_to=None,
                       configuration_details=None, **details):
        if variety is None:
            variety = name

        if configuration_details is None:
            configuration_details = {}

        slug = slugify(name, type)
        if models.Product.query.find({'slug': slug}).first():
            raise AlreadyExistingSlugException('Already exist a Product with slug: %s' % slug)

        if models.Product.query.find({'configurations.sku': sku}).first():
            raise AlreadyExistingSkuException('Already exist a Product with sku: %s' % sku)

        product = models.Product(type=type,
                                 name=name,
                                 description=description,
                                 slug=slug,
                                 details=details,
                                 active=active,
                                 valid_from=valid_from,
                                 valid_to=valid_to,
                                 configurations=[{'sku': sku,
                                                  'variety': variety,
                                                  'price': price,
                                                  'vat': vat,
                                                  'qty': qty,
                                                  'initial_quantity': initial_quantity,
                                                  'details': configuration_details}])


    def get_product(self, sku=None, _id=None, slug=None):
        if _id is not None:
            return models.Product.query.get(_id=ObjectId(_id))
        elif sku is not None:
            return models.Product.query.find({'configurations.sku': sku}).first()
        elif slug is not None:
            return models.Product.query.find({'slug': slug}).first()
        else:
            return None

    def get_products(self, type, query=None, fields=None):
        fields = fields or []
        filter = {'type': type}
        filter.update(query or {})
        return models.Product.query.find(filter, fields=fields)

    def buy_product(self, product, configuration_index, amount):
        quantity_field = 'configurations.%s.qty' % configuration_index
        result = models.DBSession.impl.update_partial(mapper(models.Product).collection,
                                                      {'_id': product._id,
                                                        quantity_field: {'$gte': amount}},
                                                      {'$inc': {quantity_field: -amount}})
        bought = result.get('updatedExisting', False)

        return bought

    def delete_product(self, product):
        product.active = False

    def create_product_configuration(self, product, sku, price=1.0, vat=0.0,
                                     qty=0, initial_quantity=0, variety=None,
                                     **configuration_details):

        product.configurations.append({'sku': sku,
                                       'variety': variety,
                                       'price': price,
                                       'vat': vat,
                                       'qty': qty,
                                       'initial_quantity': initial_quantity,
                                       'details': configuration_details})
