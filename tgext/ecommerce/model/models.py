from datetime import datetime, timedelta
from itertools import groupby, imap
from bson import ObjectId
from ming.odm.property import ORMProperty
from ming.odm import FieldProperty, ForeignIdProperty, RelationProperty, MapperExtension
from ming.odm.declarative import MappedClass
from ming import schema as s
import tg
from tg.caching import cached_property
from tgext.pluggable import app_model
from tgext.ecommerce.lib.utils import short_lang
from tgext.ecommerce.model import DBSession
import operator


class Category(MappedClass):
    class __mongometa__:
        session = DBSession
        name = 'categories'

    _id = FieldProperty(s.ObjectId)
    name = FieldProperty(s.Anything, required=True)

    @property
    def i18n_name(self):
        return self.name.get(tg.translator.preferred_language, self.name.get(tg.config.lang))


class Product(MappedClass):
    class __mongometa__:
        session = DBSession
        name = 'products'
        unique_indexes = [('slug',),
                          ('configurations.sku',)
                          ]
        indexes = [('type', 'active', ('valid_to', -1)),
                   ('type', 'category_id', 'active'),
                   ('type','active' 'name' )]

    _id = FieldProperty(s.ObjectId)
    name = FieldProperty(s.Anything, required=True)
    type = FieldProperty(s.String, required=True)
    category_id = ForeignIdProperty(Category)
    category = RelationProperty(Category)
    description = FieldProperty(s.Anything, if_missing='')
    slug = FieldProperty(s.String, required=True)
    details = FieldProperty(s.Anything, if_missing={})
    active = FieldProperty(s.Bool, if_missing=True)
    valid_from = FieldProperty(s.DateTime)
    valid_to = FieldProperty(s.DateTime)
    configurations = FieldProperty([{
        'variety': s.Anything(required=True),
        'qty': s.Int(required=True),
        'initial_quantity': s.Int(required=True),
        'sku': s.String(required=True),
        'price': s.Float(required=True),
        'vat': s.Float(required=True),
        'details': s.Anything(if_missing={}),
    }])

    def min_price_configuration(self, min_qty_getter=1):
        if isinstance(min_qty_getter, str):
            min_qty_getter = operator.attrgetter(min_qty_getter)
        else:
            min_qty_getter = lambda c: min_qty_getter

        configurations_by_price = sorted(filter(lambda conf: conf[2]['qty'] >= min_qty_getter(conf[2]),
                                                map(lambda conf: (conf[0], conf[1]['price'] * (1+conf[1]['vat']), conf[1]),
                                                    enumerate(self.configurations))),
                                         key=lambda x: x[1])
        if not configurations_by_price:
            return None, None

        return configurations_by_price[0][:2]

    @property
    def thumbnail(self):
        return tg.url(self.details['product_photos'][0]['url']) if self.details['product_photos'] else '//placehold.it/300x300'

    @property
    def i18n_name(self):
        return self.name.get(tg.translator.preferred_language, self.name.get(tg.config.lang))

    @property
    def i18n_description(self):
        return self.description.get(tg.translator.preferred_language, self.description.get(tg.config.lang))

    def i18n_configuration_variety(self, configuration):
        return configuration.variety.get(tg.translator.preferred_language, configuration.variety.get(tg.config.lang))


class CartTtlExt(MapperExtension):

    _cart_ttl = None

    @classmethod
    def cart_expiration(cls):
        if cls._cart_ttl is None:
            cls._cart_ttl = int(tg.config.get('cart.ttl', 30*60))
        return datetime.utcnow() + timedelta(seconds=cls._cart_ttl)

    def before_update(self, instance, state, sess):
        instance.expires_at = self.cart_expiration()


class Cart(MappedClass):
    class __mongometa__:
        session = DBSession
        name = 'carts'
        unique_indexes = [('user_id', )]
        indexes = [('expires_at', )]
        extensions = [CartTtlExt]

    _id = FieldProperty(s.ObjectId)
    user_id = FieldProperty(s.String, required=True)
    items = FieldProperty(s.Anything, if_missing={})
    expires_at = FieldProperty(s.DateTime, if_missing=CartTtlExt.cart_expiration)
    last_update = FieldProperty(s.DateTime, if_missing=datetime.utcnow())
    order_info = FieldProperty({
        'payment': s.Anything(if_missing={}),
        'shipment_info': {
            'receiver': s.String(),
            'address': s.String(),
            'city': s.String(),
            'province': s.String(),
            'state': s.String(),
            'zip_code': s.String(),
            'country': s.String(),
            'details': s.Anything(if_missing={})
        },
        'shipping_charges': s.Float(if_missing=0.0),
        'bill': s.Bool(if_missing=False),
        'bill_info': {
            'company': s.String(),
            'vat': s.String(),
            'address': s.String(),
            'city': s.String(),
            'province': s.String(),
            'state': s.String(),
            'zip_code': s.String(),
            'country': s.String(),
            'bill_emitted': s.Bool(if_missing=False),
            'details': s.Anything(if_missing={})
        },
        'notes': s.String(),
        'details': s.Anything(if_missing={})
    })

    @property
    def item_count(self):
        return sum([item['qty'] for item in self.items.values()])

    @property
    def subtotal(self):
        return sum([item['price']*item['qty'] for item in self.items.values()])

    @property
    def tax(self):
        return sum([item['price']*item['qty']*item['vat'] for item in self.items.values()])

    @property
    def total(self):
        return sum([item['price']*item['qty']*(1+item['vat']) for item in self.items.values()])

    @classmethod
    def expired_carts(cls):
        return cls.query.find({'expires_at': {'$lte': datetime.utcnow()}})


class OrderStatusExt(MapperExtension):
    def before_insert(self, instance, state, sess):
        status = instance.status or 'created'
        self._change_status(instance, status)
        self._store_user_name(instance)

    def before_update(self, instance, state, sess):
        if instance.status != self._prev_status(instance):
            self._change_status(instance, instance.status)

    def _change_status(self, instance, status):
        identity = tg.request.identity['user']
        changed_by = '%s %s' % (identity.name, identity.surname) if identity else None
        instance.status_changes.append({'status': status, 'changed_by': changed_by, 'changed_at': datetime.utcnow()})

    def _prev_status(self, instance):
        return instance.status_changes[-1]['status']

    def _store_user_name(self, instance):
        user_id = instance.user_id
        user_obj = app_model.User.query.get(_id=ObjectId(user_id))
        user = '%s %s' % (user_obj.name, user_obj.surname)
        instance.user = user


class Order(MappedClass):
    class __mongometa__:
        session = DBSession
        name = 'orders'
        indexes = [('user_id', ),
                   ('status_changes.changed_at', ),
                   (('user', ), ('status_changes.changed_at', )),
                   (('status', ), ('status_changes.changed_at', ))]
        extensions = [OrderStatusExt]

    _id = FieldProperty(s.ObjectId)
    user_id = FieldProperty(s.String, required=True)
    user = FieldProperty(s.String)
    payment_date = FieldProperty(s.DateTime, required=True)
    cancellation_date = FieldProperty(s.DateTime)
    creation_date = FieldProperty(s.DateTime, required=True)
    shipment_info = FieldProperty({
        'receiver': s.String(),
        'address': s.String(),
        'city': s.String(),
        'province': s.String(),
        'state': s.String(),
        'zip_code': s.String(),
        'country': s.String(),
        'details': s.Anything(if_missing={})
    })
    bill = FieldProperty(s.Bool, if_missing=False)
    billed = FieldProperty(s.Bool, if_missing=False)
    billed_date = FieldProperty(s.DateTime)
    billed_by = FieldProperty(s.String)
    bill_info = FieldProperty({
        'company': s.String(),
        'vat': s.String(),
        'address': s.String(),
        'city': s.String(),
        'province': s.String(),
        'state': s.String(),
        'zip_code': s.String(),
        'country': s.String(),
        'bill_emitted': s.Bool(),
        'details': s.Anything(if_missing={})
    })
    payer_info = FieldProperty({
        'first_name': s.String(),
        'last_name': s.String(),
        'email': s.String()
    })
    items = FieldProperty([{
        'name': s.Anything(required=True),
        'variety': s.Anything(required=True),
        'qty': s.Int(required=True),
        'sku': s.String(required=True),
        'net_price': s.Float(required=True),
        'vat': s.Float(required=True),
        'base_vat': s.Float(required=True),
        'gross_price': s.Float(required=True),
        'details': s.Anything(if_missing={})
    }])
    net_total = FieldProperty(s.Float, required=True)
    tax = FieldProperty(s.Float, required=True)
    gross_total = FieldProperty(s.Float, required=True)
    shipping_charges = FieldProperty(s.Float, required=True)
    total = FieldProperty(s.Float, required=True)
    status = FieldProperty(s.String, required=True)
    notes = FieldProperty(s.String, if_missing='')
    details = FieldProperty(s.Anything, if_missing={})
    status_changes = FieldProperty(s.Anything, if_missing=[])

    @cached_property
    def net_per_vat_rate(self):
        mapping = {}
        sorted_items = sorted(self.items, key=lambda i: i['vat'])
        for k, g in groupby(sorted_items, key=lambda i: i['vat']):
            mapping[k] = sum(imap(lambda i: i.net_price, g))

        return mapping

    @property
    def billed_by_name(self):
        user_obj = app_model.User.query.get(_id=ObjectId(self.billed_by))
        user = '%s %s' % (user_obj.name, user_obj.surname)
        return user

