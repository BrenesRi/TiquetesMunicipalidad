from odoo import models, fields, api, exceptions
from odoo.tools.float_utils import float_compare, float_is_zero

import logging
_logger = logging.getLogger(__name__)

class Tiquete(models.Model):
    _name = "pdi.tiquete"
    _description = "Módulo de Tiquetes de soporte técnico"

    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    fecha_cierre = fields.Datetime("Fecha de Solución", readonly=True, copy=False, tracking=True)

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

    #Validaciones de roles
    is_support_or_admin = fields.Boolean(compute='_compute_is_support_or_admin', store=False)

    #Validaciones
    _sql_constraints = [
    ('unique_nombre', 'UNIQUE(nombre)', 'El título del tiquete debe ser único.'),
    ('fecha_cierre_check', 'CHECK(fecha_cierre >= fecha_creacion)', 
    'La fecha de cierre debe ser posterior a la fecha de creación.'),
    ('check_estado', "CHECK(state IN ('registrado', 'abierto', 'en_revision', 'en_atencion', 'solucionado', 'cerrado', 'cancelado'))", 
    'El estado del tiquete debe ser válido.'),
    ]
    
    @api.model
    def create(self, vals):
        record = super(Tiquete, self).create(vals)
        record._send_notification_email()
        return record
    
    def _send_notification_email(self):
        admin_group = self.env.ref('Tiquetes.grupo_admin', raise_if_not_found=False)
        support_group = self.env.ref('Tiquetes.grupo_soporte', raise_if_not_found=False)
        users = (admin_group.users if admin_group else self.env['res.users']) | \
                (support_group.users if support_group else self.env['res.users'])

        if users:
            partner_ids = [pid for pid in users.mapped('partner_id.id') if pid]

            channel = self.env['mail.channel'].sudo().search([
                ('channel_type', '=', 'chat'),
                ('name', '=', 'Notificaciones Tiquetes')
            ], limit=1)

            if not channel:
                channel = self.env['mail.channel'].sudo().create({
                    'channel_partner_ids': [(4, pid) for pid in partner_ids],
                    'channel_type': 'chat',
                    'name': 'Notificaciones Tiquetes',
                })
            else:
                # Aseguramos que estén todos los usuarios
                channel.sudo().write({
                    'channel_partner_ids': [(4, pid) for pid in partner_ids]
                })

            # 🚨 Este es el paso que te falta ahora:
            channel.message_post(
                body=f"Hola, se ha creado un nuevo tiquete: <b>{self.nombre}</b>. Por favor, revísalo.",
                subtype_xmlid="mail.mt_comment",
                message_type='comment',
            )
   
    @api.depends_context('uid')
    def _compute_is_support_or_admin(self):
        current_user = self.env.user
        is_admin_or_support = (
            current_user.has_group('Tiquetes.grupo_soporte') or
            current_user.has_group('Tiquetes.grupo_admin')
        )
        for record in self:
            record.is_support_or_admin = is_admin_or_support

    @api.model
    def default_get(self, fields):
        res = super(Tiquete, self).default_get(fields)
        user = self.env.user
        res['is_support_or_admin'] = user.has_group('Tiquetes.grupo_soporte') or user.has_group('Tiquetes.grupo_admin')
        return res

    @api.depends('fecha_creacion', 'fecha_prevista')
    def _compute_duracion_prevista(self):
        for record in self:
            if record.fecha_creacion and record.fecha_prevista:
                delta = record.fecha_prevista - record.fecha_creacion.date()
                record.duracion_prevista = delta.days + 1
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
            delta = self.fecha_cierre.date() - self.fecha_creacion.date()
            self.duracion_real = delta.days #A este no se le suma 1 porque ya se cuenta el día de creación
        else:
            self.duracion_real = 0.0


    @api.constrains('duracion_prevista')
    def _check_duracion_prevista(self):
        for record in self:
            if record.duracion_prevista < -1:
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
                raise exceptions.UserError("Solo se pueden notificar tiquetes registrados")
            record.write({'state': 'abierto'})        

    def button_revision(self):
        if not (self.env.user.has_group('grupo_soporte') or self.env.user.has_group('grupo_admin')):
            raise exceptions.UserError("Solo el personal de soporte puede poner un tiquete en revisión.")
        for record in self:
            if record.state not in ['abierto']:
                raise exceptions.UserError("Para poner un tiquete en revisión, debe estar Abierto.")
            record.write({'state': 'en_revision'})

    def button_atencion(self):
        if not (self.env.user.has_group('grupo_soporte') or self.env.user.has_group('grupo_admin')):
            raise exceptions.UserError("Solo el personal de soporte puede poner un tiquete en atención.")
        for record in self:
            if record.state not in ['en_revision']:
                raise exceptions.UserError("Para poner un tiquete en atención, debe haber sido revisado.")
            record.write({'state': 'en_atencion'})

    def button_solucionado(self):
        if not (self.env.user.has_group('grupo_soporte') or self.env.user.has_group('grupo_admin')):
            raise exceptions.UserError("Solo el personal de soporte puede marcar un tiquete como solucionado.")
        for record in self:
            if record.state not in ['en_atencion']:
                raise exceptions.UserError("Para dar por solucionado un tiquete, debe haber estado en atención.")
            record.write({'state': 'solucionado'})

    def button_cerrado(self):
        for record in self:
            if record.state not in ['solucionado']:
                raise exceptions.UserError("Para cerrar un tiquete, debe haber sido solucionado.")
        for line in self:
            line.fecha_cierre = fields.Datetime.now()
            line.duracion_real = (line.fecha_cierre - line.fecha_creacion).days
            line.state = "cerrado"
            line.write({'state': 'cerrado'})
        
    def button_reabrir(self):
        for record in self:
            if record.state not in ['cerrado']:
                raise exceptions.UserError("Para reabrir un tiquete, debe haber sido cerrado.")
            record.fecha_cierre = False
            record.duracion_real = 0.0
            record.state = "en_atencion"
            record.write({'state': 'en_atencion'})
   
     # Bloquear edición del tiquete al colocarlo como "cancelado" o "cerrado"
    @api.model  
    def fields_get(self, allfields=None, attributes=None):
        fields = super(Tiquete, self).fields_get(allfields, attributes)
        if self.env.context.get('active_id'):
            tiquete = self.browse(self.env.context['active_id'])
            if tiquete.state in ['cerrado', 'cancelado']:
                for field in fields:
                    fields[field]['readonly'] = True
        return fields
    
        