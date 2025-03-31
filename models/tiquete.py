from odoo import models, fields, api, exceptions
from odoo.tools.float_utils import float_compare, float_is_zero

import logging
_logger = logging.getLogger(__name__)

class Tiquete(models.Model):
    _name = "pdi.tiquete"
    _description = "Módulo de Tiquetes de soporte técnico"

    #Para el uso de correo electrónico
    _inherit = ["mail.thread", "mail.activity.mixin"]

    alias_id = fields.Many2one(
        "mail.alias", string="Alias", 
        help="Dirección de correo utilizada para la creación de tiquetes."
    )

    #Aspectos básicos
    nombre = fields.Char("Título", required=True, tracking=True)
    description = fields.Text("Descripción", required=True, tracking=True)

    create_user_id = fields.Many2one(
        'res.users', 
        string='Reportado por', 
        index=True, 
        default=lambda self: self.env.user, 
        readonly=True
    )

    #Relaciones
    resolver_id = fields.Many2one('res.partner', string='Resuelto por', index=True, tracking=True)
    sulucion_ids = fields.One2many('pdi.tiquete.solucion', 'tiquete_id', string="Pasos de Solución")

    #Seguimiento de plazos
    fecha_creacion = fields.Datetime("Fecha de Creación", default=fields.Datetime.now, readonly=True, copy=False, tracking=True)
    fecha_prevista = fields.Date("Fecha esperada de solución", tracking=True)
    fecha_cierre = fields.Datetime("Fecha de Cierre")

    duracion_prevista = fields.Float("Duración Prevista (en días)", compute="_compute_duracion_prevista", store=True, readonly=True, tracking=True)
    duracion_real = fields.Float("Duración Real (en días)", readonly=True)
    
    #Estado y prioridad
    state = fields.Selection([
    ('registrado', '📝 Registrado'),
    ('abierto', '🚀 Abierto'),
    ('en_revision', '🔍 En Revisión'),
    ('en_atencion', '⚙️ En Atención'),
    ('solucionado', '✅ Solucionado'),
    ('cerrado', '🔒 Cerrado'),
    ('cancelado', '❌ Cancelado'),
    ], default='registrado', tracking=True)

    prioridad = fields.Selection([
    ('por_definir', '🔵 Por Definir'),
    ('baja', '🟢 Baja'),
    ('media', '🟡 Media'),
    ('alta', '🔴 Alta'),
    ('critica', '🔥 Crítica'),
    ], string="Prioridad", default='por_definir', tracking=True)

    #Validaciones
    _sql_constraints = [
    ('unique_nombre', 'UNIQUE(nombre)', 'El título del tiquete debe ser único.'),
    ('fecha_cierre_check', 'CHECK(fecha_cierre >= fecha_creacion)', 
    'La fecha de cierre debe ser posterior a la fecha de creación.'),
    ('fecha_prevista_check', 'CHECK(fecha_prevista >= fecha_creacion)', 
    'La fecha prevista debe ser posterior a la fecha de creación.'),
    ('check_estado', "CHECK(state IN ('registrado', 'abierto', 'en_revision', 'en_atencion', 'solucionado', 'cerrado', 'cancelado'))", 
    'El estado del tiquete debe ser válido.'),
    ]
    
    @api.depends('fecha_creacion', 'fecha_prevista')
    def _compute_duracion_prevista(self):
        for record in self:
            if record.fecha_creacion and record.fecha_prevista:
                delta = record.fecha_prevista - record.fecha_creacion.date()
                record.duracion_prevista = delta.days
            else:
                record.duracion_prevista = 0.0

    @api.onchange('fecha_prevista')
    def _onchange_fecha_prevista(self):
        if self.fecha_creacion and self.fecha_prevista and self.fecha_prevista < self.fecha_creacion.date():
            raise exceptions.ValidationError("La fecha prevista no puede ser anterior a la fecha de creación.")

    @api.onchange('fecha_cierre')
    def _onchange_fecha_cierre(self):
        if self.fecha_creacion and self.fecha_cierre and self.fecha_cierre < self.fecha_creacion:
            raise exceptions.ValidationError("La fecha de cierre no puede ser anterior a la fecha de creación.")
        if self.fecha_creacion and self.fecha_cierre:
            delta = self.fecha_cierre - self.fecha_creacion
            self.duracion_real = delta.days + delta.seconds / 86400
        else:
            self.duracion_real = 0.0

    @api.constrains('duracion_prevista')
    def _check_duracion_prevista(self):
        for record in self:
            if record.duracion_prevista <= 0:
                raise exceptions.ValidationError("La duración prevista debe ser un número positivo.")
    
    #Botones para cambiar el tiquete de estado
    def button_cancelar(self):
        for record in self:
            if record.state not in ['registrado', 'abierto']:
                raise exceptions.UserError("Solo se pueden cancelar tiquetes en estado Registrado o Abierto.")
            record.write({'state': 'cancelado'})

    def button_abierto(self):
        for record in self:
            if record.state not in ['registrado']:
                raise exceptions.UserError("Solo se pueden abrir tiquetes registrados")
            record.write({'state': 'abierto'})        

    def button_revision(self):
        for record in self:
            if record.state not in ['registrado', 'abierto']:
                raise exceptions.UserError("Para poner un tiquete en revisión, debe estar Registrado o Abierto.")
            record.write({'state': 'en_revision'})

    def button_atencion(self):
        for record in self:
            if record.state not in ['en_revision']:
                raise exceptions.UserError("Para poner un tiquete en atención, debe haber sido revisado.")
            record.write({'state': 'en_atencion'})

    def button_solucionado(self):
        for record in self:
            if record.state not in ['en_atencion']:
                raise exceptions.UserError("Para poner dar por solucionado un tiquete, debe haber estado en atención.")
            record.write({'state': 'solucionado'})

    def button_cerrado(self):
        for record in self:
            if record.state not in ['solucionado']:
                raise exceptions.UserError("Para cerrar un tiquete, debe haber sido solucionado.")
            record.write({'state': 'cerrado'})
    
    @api.constrains('duracion_prevista')
    def _check_duracion_prevista(self):
        for record in self:
            if record.duracion_prevista <= 0:
                raise exceptions.ValidationError("La duración prevista debe ser un número positivo.")
    
     # Bloquear edición del tiquete al colocarlo como "cancelado"
    @api.model
    def fields_get(self, allfields=None, attributes=None):
        fields = super(Tiquete, self).fields_get(allfields, attributes)
        if self.env.context.get('active_id'):
            tiquete = self.browse(self.env.context['active_id'])
            if tiquete.state == 'cancelado':
                for field in fields:
                    fields[field]['readonly'] = True
        return fields
    
        