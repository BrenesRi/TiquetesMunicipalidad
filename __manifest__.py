# -*- coding: utf-8 -*-
{
    'name': "Sistema de Tiquetes",
    'version': '16.0.1.0.0',
    'depends': ['base'],
    'author': "Ricardo Brenes Rodríguez",

    'installable': True,
    'application': True,
    'auto_install': False,
    'icon': '/Tiquetes/static/icon/logo.png',

    'summary': """
        Sistema gestor de tiquetes de soporte técnico
    """,

    'description': """
        Sistema gestor de tiquetes de soporte técnico para la Municipalidad de Coronado 
    """,

    'website': "https://www.coromuni.go.cr",
    'category': 'P.D.I.',
    'data': [
        #'security/groups.xml',
        'security/ir.model.access.csv',

        #'views/estate_property_views.xml',
        #'views/estate_property_type_views.xml',
        #'views/estate_menus.xml',
    ]
}
