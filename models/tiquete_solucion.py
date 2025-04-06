from datetime import timedelta, datetime
from odoo import api, fields, models, exceptions
from odoo.tools.float_utils import float_compare, float_is_zero

import logging
_logger = logging.getLogger(__name__)

class TiqueteSolucion(models.Model):
    _name = "pdi.tiquete.solucion"
    _description = "Paso de solución de un tiquete"

    # Basic
    description = fields.Text("Descripción", required=True, tracking=True)
    estado = fields.Selection(selection=[('final', "Solución Final"), 
                                         ('no final', "Aún no solucionado"),
                                         ], default='no final'
                                         '', string="Estado", copy=False, readonly=True, tracking=True)
    fecha_creacion = fields.Datetime("Fecha de Creación", default=fields.Datetime.now, readonly=True, copy=False)
    
    # Relation
    create_user_id = fields.Many2one(
        'res.users', 
        string='Reportado por', 
        index=True, 
        default=lambda self: self.env.user, 
        readonly=True
    )
    tiquete_id = fields.Many2one('pdi.tiquete', required=True)

    def action_accept(self):
        for line in  self:
            line.tiquete_id.resolver_id = line.create_user_id.id
            line.tiquete_id.state = "solucionado"
            line.estado = "final"
            line.tiquete_id.fecha_cierre = fields.Datetime.now()
            line.tiquete_id.duracion_real = (line.tiquete_id.fecha_cierre - line.tiquete_id.fecha_creacion).days
            _logger.info(f"TIQUETE SOLUCIONADO: {line.tiquete_id.nombre}")

