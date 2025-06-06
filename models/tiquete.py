from odoo import models, fields, api, exceptions
from odoo.tools.float_utils import float_compare, float_is_zero
from datetime import datetime, timedelta

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

    es_del_mes_actual = fields.Boolean(
        string="¿Del mes actual?",
        compute="_compute_es_del_mes_actual",
        store=True
    )

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
                channel.sudo().write({
                    'channel_partner_ids': [(4, pid) for pid in partner_ids]
                })
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            tiquete_url = f"{base_url}/web#id={self.id}&model=pdi.tiquete&view_type=form"

            message_body = f"""
            <p><strong>🆕 Nuevo Tiquete Registrado</strong></p>
            <p><strong>Título:</strong> {self.nombre}</p>
            <p><strong>Descripción:</strong><br>{self.description or 'Sin descripción'}</p>
            <p><strong>Prioridad:</strong> {dict(self._fields['prioridad'].selection).get(self.prioridad, 'No definida')}</p>
            <p><strong>Reportado por:</strong> {self.create_user_id.name}</p>
            <p><a href="{tiquete_url}" target="_blank" style="padding: 6px 12px; background-color: #1f7ed3; color: white; text-decoration: none; border-radius: 4px;">📎 Ver Tiquete en Odoo</a></p>
            """

            channel.message_post(
                body=message_body,
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

    @api.depends('fecha_creacion')
    def _compute_es_del_mes_actual(self):
        hoy = fields.Date.context_today(self)
        for record in self:
            if record.fecha_creacion:
                fecha = record.fecha_creacion.date()
                record.es_del_mes_actual = (fecha.month == hoy.month and fecha.year == hoy.year)
            else:
                record.es_del_mes_actual = False        

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
        if self.fecha_creacion and self.fecha_prevista:
            fecha_creacion_solo_fecha = fields.Date.to_date(self.fecha_creacion) - timedelta(days=1)
            if self.fecha_prevista < fecha_creacion_solo_fecha:
                raise exceptions.ValidationError("La fecha prevista no puede ser anterior a la fecha de creación.")
            
    @api.onchange('fecha_cierre')
    def _onchange_fecha_cierre(self):
        if self.fecha_creacion and self.fecha_cierre and self.fecha_cierre < self.fecha_creacion:
            raise exceptions.ValidationError("La fecha de cierre no puede ser anterior a la fecha de creación.")
        if self.fecha_creacion and self.fecha_cierre:
            delta = self.fecha_cierre.date() - self.fecha_creacion.date()
            self.duracion_real = delta.days
        else:
            self.duracion_real = 0.0

    @api.constrains('duracion_prevista')
    def _check_duracion_prevista(self):
        for record in self:
            if record.duracion_prevista < -1:
                raise exceptions.ValidationError("La duración prevista debe ser un número positivo.")
            
    def _notificar_cambio_estado_usuario(self, nuevo_estado):
        for record in self:
            partner = record.create_user_id.partner_id
            if not partner:
                continue  # No hay a quién notificar

            estado_emoji = dict(self._fields['state'].selection).get(nuevo_estado, nuevo_estado)

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            tiquete_url = f"{base_url}/web#id={record.id}&model=pdi.tiquete&view_type=form"

            message_body = f"""
            <p><strong>🔔 Cambio de estado del tiquete</strong></p>
            <p>El tiquete <strong>{record.nombre}</strong> ha cambiado su estado a <strong>{estado_emoji}</strong>.</p>
            <p><a href="{tiquete_url}" target="_blank" style="padding: 6px 12px; background-color: #1f7ed3; color: white; text-decoration: none; border-radius: 4px;">📎 Ver Tiquete en Odoo</a></p>
            """

            # Buscar o crear un canal privado 1:1 con el partner
            channel = self.env['mail.channel'].sudo().search([
                ('channel_type', '=', 'chat'),
                ('channel_partner_ids', 'in', [partner.id]),
                ('channel_partner_ids', 'in', [self.env.user.partner_id.id]),
                ('name', '=', f'{partner.name} - Notificación Tiquete')
            ], limit=1)

            if not channel:
                channel = self.env['mail.channel'].sudo().create({
                    'channel_partner_ids': [(4, partner.id), (4, self.env.user.partner_id.id)],
                    'channel_type': 'chat',
                    'name': f'{partner.name} - Notificación Tiquete',
                })

            # Enviar mensaje
            channel.message_post(
                body=message_body,
                subtype_xmlid="mail.mt_comment",
                message_type='comment',
            )

    def write(self, vals):
        estado_anterior = {rec.id: rec.state for rec in self}
        result = super().write(vals)

        if 'state' in vals:
            for record in self:
                estado_viejo = estado_anterior.get(record.id)
                estado_nuevo = vals.get('state')
                if estado_viejo != estado_nuevo and estado_nuevo in ['en_atencion', 'solucionado', 'cerrado']:
                    record._notificar_cambio_estado_usuario(estado_nuevo)
        return result
    
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
    
        