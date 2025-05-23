# -*- coding: utf-8 -*-
{
    'name': "Sistema de Tiquetes",
    'version': '16.0.1.0.0',
    'depends': ['base', 'mail'],
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
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/tiquete_security.xml',

        'views/tiquetes_general_views.xml',
        'views/tiquete_solucion_views.xml',

        'data/email_templates.xml',
    ]
}
