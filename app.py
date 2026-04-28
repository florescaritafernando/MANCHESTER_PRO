"""
🧾 APP DE CONVERSIÓN XML A PDF - TICKET 80mm
"""

import xml.etree.ElementTree as ET
from fpdf import FPDF
import os
import tempfile
from typing import Dict, Any, Optional
import base64
from datetime import datetime
import qrcode
import logging
import uuid
from functools import wraps
from flask import Flask, request, send_file, render_template_string, jsonify, session, redirect, url_for

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'manchester_pro_secret_key_2024'

# Configuración de la app
CONFIG = {
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB max
    'ALLOWED_EXTENSIONS': ['.xml', '.csv'],
    'DEFAULT_FORMAT': 'ticket',
    'PAGE_WIDTH': 80,
}


class YapesPDF:
    """Clase para generar PDF de YAPES"""
    
    def __init__(self, csv_path: str, output_path: str):
        self.csv_path = csv_path
        self.output_path = output_path
        self.data = []
        
    def parse_csv(self) -> bool:
        """Parsear archivo CSV"""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if len(lines) < 2:
                return False
            
            for line in lines[1:]:
                if line.strip():
                    # Separar por coma, manejar comas dentro de valores con comillas
                    import re
                    parts = []
                    in_quote = False
                    current = ""
                    for char in line.strip():
                        if char == '"':
                            in_quote = not in_quote
                        elif char == ',' and not in_quote:
                            parts.append(current)
                            current = ""
                        else:
                            current += char
                    parts.append(current)
                    
                    # Limpiar comillas y espacios
                    parts = [p.strip().strip('"').strip("'") for p in parts]
                    
                    if len(parts) >= 2 and parts[0] and parts[1]:
                        # Parsear monto manteniendo decimales
                        monto_str = parts[1].strip()
                        # Reemplazar coma por punto
                        monto_str = monto_str.replace(',', '.')
                        
                        try:
                            monto = float(monto_str)
                        except ValueError:
                            logger.warning(f"Monto inválido: {parts[1]}, usando 0")
                            monto = 0.0
                        
                        # Parsear fecha
                        fecha_raw = parts[2].strip() if len(parts) > 2 else datetime.now().strftime('%d/%m/%Y')
                        try:
                            fecha_dt = datetime.strptime(fecha_raw, '%d/%m/%Y')
                            fecha = fecha_dt.strftime('%d/%m/%Y')
                        except:
                            fecha = datetime.now().strftime('%d/%m/%Y')
                        
                        self.data.append({
                            'nombre': parts[0].upper(),
                            'monto': monto,
                            'fecha': fecha
                        })
            
            return len(self.data) > 0
        except Exception as e:
            logger.error(f"Error parseando CSV: {e}")
            return False
    
    def generate_pdf(self):
        """Generar PDF de YAPES"""
        from collections import defaultdict
        
        # Agrupar por fecha y nombre (manteniendo todos los montos)
        agrupado = defaultdict(lambda: defaultdict(list))
        for item in self.data:
            agrupado[item['fecha']][item['nombre']].append(item['monto'])
        
        # Obtener todas las fechas
        fechas = sorted(agrupado.keys(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
        
        # Ancho de página
        page_width = 80
        pdf = FPDF(orientation='P', unit='mm', format=(page_width, 200))
        pdf.set_margins(0, 0, 0)
        pdf.set_auto_page_break(auto=True, margin=3)
        pdf.add_page()
        
        # Encabezado
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 5, "RESUMEN YAPES RECIBIDOS", 0, 1, 'C')
        
        pdf.ln(1)
        pdf.cell(0, 1, "", "T", 1)
        
        # Por cada fecha
        for fecha in fechas:
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 5, f"Fecha: {fecha}", 0, 1, 'L')
            pdf.ln(2)
            
            nombres = sorted(agrupado[fecha].keys())
            col_width = page_width / 2
            
            if len(nombres) == 1:
                # Una sola columna
                nombre = nombres[0]
                montos = agrupado[fecha][nombre]
                
                pdf.set_font("Arial", 'B', 20)
                pdf.cell(0, 4, f"{nombre}", 0, 1, 'L')
                pdf.ln(4)
                
                pdf.set_font("Arial", '', 15)
                for monto in montos:
                    pdf.cell(3, 5, "-", 0, 0, 'L')
                    pdf.cell(10, 5, "S/.", 0, 0, 'L')
                    pdf.cell(0, 5, f"{monto:.2f}", 0, 1, 'R')
                    pdf.ln(1)

                # Total individual por nombre
                pdf.ln(2)
                total_nombre = sum(montos)
                pdf.set_font("Arial", 'B', 20)
                pdf.cell(0, 5, f"TOTAL: S/. {total_nombre:.2f}", 0, 1, 'R')
                pdf.ln(3)
            else:
                # Dos columnas
                for i in range(0, len(nombres), 2):
                    nombre1 = nombres[i] if i < len(nombres) else ""
                    montos1 = agrupado[fecha][nombre1] if nombre1 else []
                    total1 = sum(montos1)
                    
                    nombre2 = nombres[i+1] if i+1 < len(nombres) else ""
                    montos2 = agrupado[fecha][nombre2] if nombre2 else []
                    total2 = sum(montos2) if nombre2 else 0
                    
                    # Nombres
                    pdf.set_font("Arial", 'B', 10)
                    pdf.cell(col_width, 4, f"{nombre1}", 0, 0, 'C')
                    if nombre2:
                        pdf.cell(col_width, 4, f"{nombre2}", 0, 1, 'C')
                    else:
                        pdf.cell(col_width, 4, "", 0, 1, 'L')
                    
                    # Guardar posición Y para montos columna 2
                    y_start = pdf.get_y()
                    
                    # Montos columna 1 con padding
                    pdf.set_font("Arial", '', 15)
                    for monto in montos1:
                        pdf.cell(3, 5, "-", 0, 0, 'L')
                        pdf.cell(10, 5, "S/.", 0, 0, 'L')
                        pdf.cell(col_width - 15, 5, f"{monto:.2f}", 0, 1, 'L')
                    
                    # Total individual columna 1
                    pdf.set_font("Arial", 'B', 20)
                    pdf.cell(col_width - 10, 5, "TOTAL:", 0, 0, 'L')
                    pdf.cell(10, 5, f"S/. {total1:.2f}", 0, 1, 'R')
                    
                    # Montos columna 2
                    if nombre2:
                        pdf.set_y(y_start)
                        pdf.set_font("Arial", '', 9)
                        for monto in montos2:
                            pdf.cell(col_width + 3, 5, "-", 0, 0, 'L')
                            pdf.cell(10, 5, "S/.", 0, 0, 'L')
                            pdf.cell(col_width, 5, f"{monto:.2f}", 0, 1, 'R')
                        
                        # Total individual columna 2
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(col_width + 3, 5, "", 0, 0)
                        pdf.cell(col_width - 10, 5, "TOTAL:", 0, 0, 'L')
                        pdf.cell(10, 5, f"S/. {total2:.2f}", 0, 1, 'R')
                    else:
                        # Si no hay nombre2, completar espacio
                        pdf.set_y(y_start + max(len(montos1), 1) * 5 + 5)
                    
                    pdf.ln(3)
        
        pdf.output(self.output_path)
        logger.info(f"PDF YAPES generado: {self.output_path}")


def log_request(f):
    """Decorador para logging de requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"Request: {request.method} {request.path}")
        return f(*args, **kwargs)
    return decorated_function


def safe_div(a: float, b: float) -> float:
    """División segura que maneja errores de tipo"""
    try:
        return float(a) / float(b)
    except (TypeError, ZeroDivisionError, ValueError):
        return 0.0


class FacturaXMLtoPDF:
    """Clase principal para conversión de XML a PDF"""
    
    def __init__(self, xml_path: str, output_path: str, extra_data: Optional[Dict[str, Any]] = None):
        self.xml_path = xml_path
        self.output_path = output_path
        self.data: Dict[str, Any] = {}
        self.page_width = CONFIG['PAGE_WIDTH']
        self.extra_data = extra_data or {}
        self.errors: list = []
        
    def add_error(self, message: str):
        """Agregar error al historial"""
        self.errors.append(message)
        logger.error(f"Error: {message}")
    
    def parse_xml(self) -> bool:
        """Parsear archivo XML"""
        try:
            if not os.path.exists(self.xml_path):
                self.add_error(f"Archivo no encontrado: {self.xml_path}")
                return False
            
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
            
            namespaces = {
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
                'ds': 'http://www.w3.org/2000/09/xmldsig#'
            }
            
            # Datos básicos
            self.data['monto_letras'] = ''
            self.data['forma_pago'] = ''
            
            # Extraer notes
            for note in root.findall('.//cbc:Note', namespaces):
                note_text = note.text or ''
                if note.get('languageLocaleID') == "1000":
                    self.data['monto_letras'] = note_text
                elif note.get('languageID') == "L":
                    self.data['forma_pago'] = note_text
            
            # Datos principales
            self.data['numero_factura'] = self._get_text(root, './/cbc:ID', namespaces)
            self.data['fecha_emision'] = self._get_text(root, './/cbc:IssueDate', namespaces)
            self.data['hora_emision'] = self._get_text(root, './/cbc:IssueTime', namespaces)
            
            # Tipo de documento
            numero = self.data.get('numero_factura', '')
            self.data['tipo_documento'] = "FACTURA" if numero and numero[0].upper() == 'F' else "BOLETA DE VENTA"
            
            # Datos del emisor
            emisor = root.find('.//cac:AccountingSupplierParty/cac:Party', namespaces)
            if emisor is not None:
                self.data['emisor_nombre'] = self._get_text(emisor, './/cbc:Name', namespaces) or \
                                             self._get_text(emisor, './/cbc:RegistrationName', namespaces)
                self.data['emisor_ruc'] = self._get_text(emisor, './/cac:PartyIdentification/cbc:ID', namespaces) or \
                                          self._get_text(emisor, './/cbc:ID', namespaces)
                self.data['emisor_direccion'] = self._get_text(emisor, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['emisor_distrito'] = self._get_text(emisor, './/cbc:District', namespaces)
                self.data['emisor_departamento'] = self._get_text(emisor, './/cbc:CityName', namespaces)
            
            # Datos del cliente
            cliente = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces)
            if cliente is not None:
                self.data['cliente_nombre'] = self._get_text(cliente, './/cbc:RegistrationName', namespaces)
                self.data['cliente_ID'] = self._get_text(cliente, './/cac:PartyIdentification/cbc:ID', namespaces) or \
                                         self._get_text(cliente, './/cbc:ID', namespaces)
                self.data['cliente_direccion'] = self._get_text(cliente, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['cliente_distrito'] = self._get_text(cliente, './/cbc:District', namespaces)
                self.data['cliente_provincia'] = self._get_text(cliente, './/cbc:CountrySubentity', namespaces)
                self.data['cliente_departamento'] = self._get_text(cliente, './/cbc:CityName', namespaces)
            
            # Guía de remisión
            self.data['cliente_guia'] = self._get_text(root, './/cac:DespatchDocumentReference/cbc:ID', namespaces)
            
            # Totales
            self.data['total_venta'] = float(self._get_text(root, './/cac:TaxSubtotal/cbc:TaxableAmount', namespaces, '0.0'))
            self.data['total_igv'] = float(self._get_text(root, './/cac:TaxTotal/cbc:TaxAmount', namespaces, '0.0'))
            self.data['total_pagar'] = float(self._get_text(root, './/cac:LegalMonetaryTotal/cbc:PayableAmount', namespaces, '0.0'))
            
            # Items
            self.data['items'] = []
            for item in root.findall('.//cac:InvoiceLine', namespaces):
                item_data = {
                    'id': self._get_text(item, './/cac:SellersItemIdentification/cbc:ID', namespaces),
                    'unidad': self._get_text(item, './/cbc:Note', namespaces),
                    'descripcion': self._get_text(item, './/cbc:Description', namespaces),
                    'cantidad': float(self._get_text(item, './/cbc:InvoicedQuantity', namespaces, '0')),
                    'precio_unitario': float(self._get_text(item, './/cac:Price/cbc:PriceAmount', namespaces, '0.00')),
                    'total': float(self._get_text(item, './/cbc:LineExtensionAmount', namespaces, '0.00'))
                }
                self.data['items'].append(item_data)
            
            # Datos para QR
            self.data['tipo_codigo_invoice'] = self._get_text(root, './/cbc:InvoiceTypeCode', namespaces)
            self.data['tipo_doc_cli'] = self._get_text(
                root, 
                './/cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID', 
                namespaces, 
                attr='schemeID'
            )
            
            # Digest value
            namespaces_ds = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
            digest_node = root.find('.//ds:DigestValue', namespaces_ds)
            self.data['digest_value'] = digest_node.text if digest_node is not None else ""
            
            self.data.update(self.extra_data)
            
            logger.info(f"XML parseado: {self.data.get('numero_factura', 'N/A')}")
            return True
            
        except Exception as e:
            self.add_error(f"Error al parsear XML: {str(e)}")
            return False
    
    def _get_text(self, node, path: str, namespaces: Dict, default: str = '-', attr: str = None) -> str:
        """Obtener texto de manera segura"""
        if node is None:
            return default
        try:
            found = node.find(path, namespaces)
            if found is not None:
                if attr:
                    return found.get(attr, default)
                return found.text if found.text else default
        except Exception:
            pass
        return default
    
    def format_currency(self, amount: str) -> str:
        """Formatear monto como moneda"""
        try:
            return f"S/. {float(amount):.2f}"
        except (ValueError, TypeError):
            return "S/. 0.00"
    
    def calculate_total_height(self) -> float:
        """Calcular altura total del PDF"""
        pdf_temp = FPDF(orientation='P', unit='mm', format=(self.page_width, 300))
        pdf_temp.set_margins(0, 0, 0)
        pdf_temp.add_page()
        pdf_temp.set_font("Arial", '', 10)
        
        y = 2
        
        # Logo
        if os.path.exists("images/logo_manchester.png"):
            y += safe_div(40, 3) + 6
        
        # Encabezado emisor
        y += 4
        emisor_nombre = self.data.get('emisor_nombre', 'N/A')
        y += 8 if len(emisor_nombre) > 35 else 4
        y += 4
        y += 4  # Dirección
        y += 1 + 2 + 4 + 5 + 1 + 2 + 4 + 4 + 1 + 2 + 4 + 1 + 2
        
        # Cliente
        cliente_nombre = self.data.get('cliente_nombre', 'N/A').upper()
        y += 8 if len(cliente_nombre) > 25 else 4
        y += 1
        c_dir = (self.data.get('cliente_direccion', '') or "").strip()
        y += 8 if len(c_dir) > 24 else 4
        
        extras = [p for p in [
            self.data.get('cliente_departamento', ''),
            self.data.get('cliente_provincia', ''),
            self.data.get('cliente_distrito', '')
        ] if p and p.strip()]
        y += 1 + (8 if len(" - ".join(extras)) > 24 else 4) if extras else 0
        
        y += 2 + 1 + 2 + 4 + 1 + 1 + 2 + 1 + 2 + 1 + 2
        
        # Items
        pdf_temp.set_font("Arial", '', 8)
        for item in self.data.get('items', []):
            descripcion = str(item.get('descripcion', ''))
            lineas = 1
            if descripcion:
                palabras = descripcion.split()
                linea_actual = ""
                for palabra in palabras:
                    prueba_linea = f"{linea_actual} {palabra}".strip()
                    if pdf_temp.get_string_width(prueba_linea) <= 22:
                        linea_actual = prueba_linea
                    else:
                        lineas += 1
                        linea_actual = palabra
            y += max(lineas, 1) * 3 + 2
        
        y += 2 + 5 + 5 + 8 + 2
        
        # Totales
        monto_l = self.data.get('monto_letras', '')
        y += 8 if len(monto_l) > 24 else 4
        
        y += safe_div(30, 3) + 20 + 4 + 4 + 20
        
        return max(100, min(800, y + 30))
    
    def generate_pdf(self, output_format: str = 'ticket'):
        """Generar PDF según formato"""
        if output_format == 'ticket':
            self._generate_ticket_pdf()
        elif output_format == 'shipping_label':
            self._generate_shipping_label_pdf()
        else:
            raise ValueError(f"Formato no válido: {output_format}")
    
    def _generate_shipping_label_pdf(self):
        """Generar etiqueta de envío 100x150mm sin márgenes"""
        label_width = 100
        label_height = 150
        
        pdf = FPDF(orientation='P', unit='mm', format=(label_width, label_height))
        pdf.set_margins(0, 0, 0)
        pdf.add_page()
        pdf.set_auto_page_break(auto=False)
        
        emisor_nombre = self.data.get('emisor_nombre', 'N/A').upper()
        emisor_ruc = self.data.get('emisor_ruc', 'N/A')
        
        logo_path = "images/logo_manchester.png"
        logo_width = 35
        pdf.set_y(0)
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=0, y=0, w=logo_width)
            pdf.set_y(20)
        else:
            pdf.set_font("Arial", 'B', 14)
            pdf.set_xy(0, 0)
            pdf.cell(35, 7, "MANCHESTER", 0, 0, 'L')
            pdf.set_y(12)
        
        remitente_x = label_width - 45
        pdf.set_y(0)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_xy(remitente_x, 0)
        pdf.cell(45, 5, "REMITENTE", 'TLR', 1, 'C')
        
        pdf.set_font("Arial", '', 7)
        pdf.set_xy(remitente_x, pdf.get_y())
        pdf.set_char_spacing(0.5)
        pdf.cell(45, 4, f"RUC: {emisor_ruc}", 'LR', 1, 'C')
        pdf.set_char_spacing(0.0)
        
        pdf.set_font("Arial", 'B', 8)
        pdf.set_xy(remitente_x, pdf.get_y())
        
        if pdf.get_string_width(emisor_nombre) > 40:
            pdf.set_font("Arial", 'B', 7)
            pdf.multi_cell(45, 4, emisor_nombre, 'BLR', 'C')
        else:
            pdf.cell(45, 4, emisor_nombre, 'BLR', 1, 'C')
        
        pdf.line(0, pdf.get_y() + 1, label_width, pdf.get_y() + 1)
        pdf.set_y(pdf.get_y() + 3)
        
        cliente_id = self.data.get('cliente_ID', '')
        cliente_nombre = self.data.get('cliente_nombre', 'N/A').upper()
        
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 5, "DATOS DESTINATARIO", 0, 1, 'C')
        
        pdf.set_font("Arial", 'B', 20)
        
        if pdf.get_string_width(cliente_nombre) > 200:
            pdf.set_font("Arial", 'B', 15)
            pdf.multi_cell(90, 8, cliente_nombre, 0, 'L')
        else:
            pdf.multi_cell(90, 8, cliente_nombre, 0, 'L')
        
        pdf.ln(2)
        
        pdf.set_font("Arial", '', 15)
        pdf.set_char_spacing(0.5)
        id_label = "RUC" if len(cliente_id) == 11 else ("DNI" if len(cliente_id) == 8 else "CE")
        pdf.cell(90, 5, f"{id_label}: {cliente_id}", 0, 1, 'L')
        pdf.set_char_spacing(0.0)
        pdf.ln(1)
        
        cliente_dir = self.data.get('cliente_direccion', '')
        cliente_dis = self.data.get('cliente_distrito', '')
        cliente_pro = self.data.get('cliente_provincia', '')
        cliente_dep = self.data.get('cliente_departamento', '')
        
        invalidos = ['N/A', 'n/a', '-', '--', '---', '', None]
        
        c_dir = cliente_dir.strip() if cliente_dir and cliente_dir.strip() not in invalidos else "-"
        
        direccion_partes = [cliente_dep, cliente_pro, cliente_dis]
        direccion_ciudad = [p.strip() for p in direccion_partes if p and p.strip() not in invalidos]
        direccion_completa = " - ".join(direccion_ciudad).upper()
        
        pdf.set_font("Arial", '', 8)
        pdf.cell(90, 5, "DIRECCIÓN DE ENVIO:", 0, 1, 'L')
        pdf.set_font("Arial", 'B', 15)
        pdf.ln(1)
        
        pdf.multi_cell(90, 6, c_dir.upper(), 'B', 'L')
        
        if direccion_completa:
            pdf.ln(1)
            pdf.set_font("Arial", '', 8)
            pdf.cell(90, 5, "CIUDAD:", 0, 1, 'L')
            pdf.set_font("Arial", 'B', 15)
            pdf.ln(1)
            pdf.multi_cell(90, 5, direccion_completa, 'B', 'L')
        
        pdf.ln(3)
        
        agency_name = self.data.get('agency_name', '').upper()
        other_notes = self.data.get('other_notes', '').upper()
        
        if agency_name:
            ancho_label = 20
            ancho_valor = 70
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "AGENCIA:", 0, 0, 'L')
            
            if pdf.get_string_width(agency_name) > 100:
                pdf.set_font("Arial", 'B', 8)
                pdf.multi_cell(ancho_valor, 4, agency_name, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, agency_name, 0, 'L')
            pdf.ln(1)
        
        pdf.ln(2)
        if other_notes:
            ancho_label = 15
            ancho_valor = 75
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "OTROS:", 0, 0, 'L')
            
            pdf.set_font("Arial", '', 10)
            
            if pdf.get_string_width(other_notes) > 100:
                pdf.set_font("Arial", '', 8)
                pdf.multi_cell(ancho_valor, 4, other_notes, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, other_notes, 0, 'L')
            pdf.ln(1)
        
        y_qr_start = label_height - 10 - 20
        qr_width = 20
        qr_x = 0
        y_qr_start = label_height - 10 - qr_width
        
        qr_path = "images/qr_mostrario.png"
        if os.path.exists(qr_path):
            pdf.image(qr_path, x=qr_x, y=y_qr_start, w=qr_width)
        else:
            pdf.set_fill_color(200, 200, 200)
            pdf.rect(qr_x, y_qr_start, qr_width, qr_width, 'F')
            pdf.set_font("Arial", '', 8)
            pdf.set_xy(qr_x, y_qr_start + 12)
            pdf.cell(qr_width, 5, "QR", 0, 0, 'C')
        
        pdf.set_font("Arial", '', 6)
        pdf.set_xy(qr_x, y_qr_start + qr_width + 1)
        pdf.cell(qr_width, 4, "CATÁLOGO", 0, 0, 'C')
        
        num_documento = self.data.get('numero_factura', 'N/A')
        fecha = self.data.get('fecha_emision', 'N/A')
        guia_remision = self.data.get('cliente_guia', 'N/A')
        
        fecha_formateada = fecha
        
        if fecha != 'N/A':
            try:
                objeto_fecha = datetime.strptime(fecha, '%Y-%m-%d')
                fecha_formateada = objeto_fecha.strftime('%d/%m/%Y')
            except ValueError:
                pass
        
        info_x = qr_x + qr_width + 5
        info_width = label_width - info_x
        
        pdf.set_xy(info_x, y_qr_start)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.2)
        pdf.set_fill_color(255, 255, 255)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_char_spacing(1)
        pdf.cell(info_width, 5, f"N° DE DOC.: {num_documento}", 1, 1, 'C', True)
        
        pdf.set_x(info_x)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(info_width, 5, f"FECHA: {fecha_formateada}", 1, 1, 'C', True)
        
        if guia_remision != 'N/A' and guia_remision.strip():
            pdf.set_x(info_x)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(info_width, 5, f"GUÍA: N° {guia_remision}", 1, 1, 'C', True)
        
        pdf.set_char_spacing(0)
        
        pdf.output(self.output_path)
        logger.info(f"Etiqueta de envío generada: {self.output_path} (100mm x 150mm)")
        
        agency_name = self.data.get('agency_name', '').upper()
        other_notes = self.data.get('other_notes', '').upper()
        
        if agency_name:
            ancho_label = 20
            ancho_valor = 70
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "AGENCIA:", 0, 0, 'L')
            
            if pdf.get_string_width(agency_name) > 100:
                pdf.set_font("Arial", 'B', 8)
                pdf.multi_cell(ancho_valor, 4, agency_name, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, agency_name, 0, 'L')
            pdf.ln(1)
        
        pdf.ln(2)
        if other_notes:
            ancho_label = 15
            ancho_valor = 75
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "OTROS:", 0, 0, 'L')
            
            pdf.set_font("Arial", '', 10)
            
            if pdf.get_string_width(other_notes) > 100:
                pdf.set_font("Arial", '', 8)
                pdf.multi_cell(ancho_valor, 4, other_notes, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, other_notes, 0, 'L')
            pdf.ln(1)
        
y_qr_start = label_height - 10 - 20
        qr_width = 20
        qr_x = 5
        y_qr_start = label_height - 10 - qr_width
        
        qr_path = "images/qr_mostrario.png"
        if os.path.exists(qr_path):
            pdf.image(qr_path, x=qr_x, y=y_qr_start, w=qr_width)
        else:
            pdf.set_fill_color(200, 200, 200)
            pdf.rect(qr_x, y_qr_start, qr_width, qr_width, 'F')
            pdf.set_font("Arial", '', 8)
            pdf.set_xy(qr_x, y_qr_start + 12)
            pdf.cell(qr_width, 5, "QR", 0, 0, 'C')
        
        pdf.set_font("Arial", '', 6)
        pdf.set_xy(qr_x, y_qr_start + qr_width + 1)
        pdf.cell(qr_width, 4, "CATÁLOGO", 0, 0, 'C')
        
        num_documento = self.data.get('numero_factura', 'N/A')
        fecha = self.data.get('fecha_emision', 'N/A')
        guia_remision = self.data.get('cliente_guia', 'N/A')
        
        fecha_formateada = fecha
        
        if fecha != 'N/A':
            try:
                objeto_fecha = datetime.strptime(fecha, '%Y-%m-%d')
                fecha_formateada = objeto_fecha.strftime('%d/%m/%Y')
            except ValueError:
                pass
        
        info_x = qr_x + qr_width + 5
        info_width = label_width - 5 - info_x
        
        pdf.set_xy(info_x, y_qr_start)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.2)
        pdf.set_fill_color(255, 255, 255)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_char_spacing(1)
        pdf.cell(info_width, 5, f"N° DE DOC.: {num_documento}", 1, 1, 'C', True)
        
        pdf.set_x(info_x)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(info_width, 5, f"FECHA: {fecha_formateada}", 1, 1, 'C', True)
        
        if guia_remision != 'N/A' and guia_remision.strip():
            pdf.set_x(info_x)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(info_width, 5, f"GUÍA: N° {guia_remision}", 1, 1, 'C', True)
        
        pdf.set_char_spacing(0)
        
        pdf.output(self.output_path)
        logger.info(f"Etiqueta de envío generada: {self.output_path} (100mm x 150mm)")

    def _generate_qr(self, pdf):
        """Generar código QR"""
        ruc = self.data.get('emisor_ruc', '')
        tipo = self.data.get('tipo_codigo_invoice', '01')
        serie, correlativo = self.data.get('numero_factura', '001-000001').split('-')[:2]
        
        val_igv = safe_div(float(self.data.get('total_igv', '0')), 1)
        val_total = safe_div(float(self.data.get('total_pagar', '0')), 1)
        
        fecha = self.data.get('fecha_emision', '')
        tipo_doc_cli = self.data.get('tipo_doc_cli', '')
        ruc_cli = self.data.get('cliente_ID', '')
        digest = self.data.get('digest_value', '')
        
        cadena_qr = f"{ruc}|{tipo}|{serie}|{correlativo}|{val_igv:.2f}|{val_total:.2f}|{fecha}|{tipo_doc_cli}|{ruc_cli}|{digest}|"
        
        try:
            qr_img = qrcode.make(cadena_qr)
            qr_path = "images/qr_mostrario.png"
            qr_img.save(qr_path)
            
            if ruc and os.path.exists(qr_path):
                img_w = 30
                img_x = safe_div(self.page_width - img_w, 2)
                pdf.image(qr_path, x=img_x, y=pdf.get_y(), w=img_w)
                pdf.set_y(pdf.get_y() + safe_div(img_w, 3) + 20)
        except Exception as e:
            logger.warning(f"Error generando QR: {e}")        
    
    def _generate_ticket_pdf(self):
        """Generar ticket 80mm"""
        page_height = self.calculate_total_height()
        
        pdf = FPDF(orientation='P', unit='mm', format=(self.page_width, page_height))
        pdf.set_margins(0, 0, 0)
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        
        # Logo
        image_path = "images/logo_manchester.png"
        if os.path.exists(image_path):
            try:
                pdf.image(image_path, x=20, y=3, w=40)
                pdf.ln(safe_div(40, 3) + 4)
            except Exception as e:
                logger.warning(f"Error cargando logo: {e}")
                pdf.ln(5)
        else:
            pdf.ln(5)
        
        pdf.ln(1)
        
        # Encabezado emisor
        pdf.set_font("Arial", '', 10)
        emisor_nombre = self.data.get('emisor_nombre', 'N/A')
        if len(emisor_nombre) > 35:
            pdf.multi_cell(0, 4, emisor_nombre, 0, 'C')
        else:
            pdf.cell(0, 4, emisor_nombre, 0, 1, 'C')
        
        pdf.cell(0, 4, f"RUC: {self.data.get('emisor_ruc', 'N/A')}", 0, 1, 'C')
        
        # Dirección emisor
        emisor_dir = self.data.get('emisor_direccion', '')
        emisor_dis = self.data.get('emisor_distrito', '')
        emisor_dep = self.data.get('emisor_departamento', '')
        dir_completa = f"{emisor_dir}"
        if emisor_dis:
            dir_completa += f" - {emisor_dis}"
        if emisor_dep:
            dir_completa += f" - {emisor_dep}"
        
        if len(dir_completa) > 35:
            pdf.multi_cell(0, 4, dir_completa, 0, 'C')
        else:
            pdf.cell(0, 4, dir_completa, 0, 1, 'C')
        
        pdf.ln(1)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        # Tipo documento
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 4, f"{self.data.get('tipo_documento', 'COMPROBANTE')} ELECTRÓNICA", 0, 1, 'C')
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 5, self.data.get('numero_factura', 'N/A'), 0, 1, 'C')
        
        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        # Datos cliente
        pdf.set_font("Arial", '', 10)
        cliente_id = self.data.get('cliente_ID', '')
        label_id = "RUC:" if len(cliente_id) == 11 else ("DNI:" if len(cliente_id) == 8 else "CE:")
        pdf.cell(10, 4, label_id, 0, 0)
        pdf.set_font("Arial", '', 12)
        pdf.cell(80, 4, cliente_id, 0, 1)
        
        pdf.ln(1)
        pdf.set_font("Arial", '', 10)
        cliente_nombre = self.data.get('cliente_nombre', 'N/A').upper()
        label = "RAZÓN SOCIAL:" if len(cliente_id) == 11 else "CLIENTE:"
        if len(cliente_nombre) > 25:
            pdf.multi_cell(0, 4, f"{label} {cliente_nombre}", 0)
        else:
            pdf.cell(0, 4, f"{label} {cliente_nombre}", 0, 1)
        
        pdf.ln(1)
        
        # Dirección cliente
        c_dir = (self.data.get('cliente_direccion', '') or "").strip()
        c_dis = self.data.get('cliente_distrito', '')
        c_pro = self.data.get('cliente_provincia', '')
        c_dep = self.data.get('cliente_departamento', '')
        
        pdf.set_font("Arial", '', 10)
        if len(c_dir) > 24:
            pdf.multi_cell(0, 4, f"DIRECCIÓN: {c_dir.upper()}", 0)
        else:
            pdf.cell(0, 4, f"DIRECCIÓN: {c_dir.upper()}", 0, 1, 'L')
        
        extras = [p for p in [c_dep, c_pro, c_dis] if p and p.strip()]
        if extras:
            pdf.ln(1)
            txt = f"CIUDAD: {' - '.join(extras).upper()}"
            if len(txt) > 24:
                pdf.multi_cell(0, 4, txt, 0, 'L')
            else:
                pdf.cell(0, 4, txt, 0, 1, 'L')
        
        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        # Guía de remisión
        guia = self.data.get('cliente_guia', '')
        if guia and guia not in ['', 'N/A', '-']:
            pdf.cell(35, 4, "GUÍA DE REMISIÓN: ", 0, 0)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(45, 4, f"N° {guia}", 0, 1)
            pdf.ln(1)
        
        # Forma de pago
        pdf.set_font("Arial", '', 10)
        f_pago = self.data.get('forma_pago', '').upper()
        pdf.cell(0, 4, f"FORMA DE PAGO: {f_pago}" if f_pago else "", 0, 1)
        
        pdf.ln(1)
        # Fecha
        fecha = self.data.get('fecha_emision', 'N/A')
        if fecha != 'N/A':
            try:
                fecha = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                pass
        hora = self.data.get('hora_emision', '')
        pdf.cell(0, 4, f"FECHA DE EMISIÓN: {fecha} {hora}".strip(), 0, 1)
        
        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        # Tabla de items
        anchuras = [8, 14, 10, 22, 10, 16]
        pdf.set_draw_color(255, 255, 255)
        pdf.set_font("Arial", '', 7)
        
        headers = ["COD.", "CANT.", "UNID.", "DESCRIPCIÓN", "V.UNIT.", "V.VENTA"]

        for i, h in enumerate(headers):
            pdf.cell(anchuras[i], 1, h, 1, 0, 'C')
        
        pdf.set_draw_color(0, 0, 0)

        pdf.ln(2)
        pdf.cell(0, 2, "", "T", 1)
        
        
        pdf.set_font("Arial", '', 8)
        
        pdf.set_draw_color(255, 255, 255)
        
        pdf.set_font("Arial", '', 8)
        for item in self.data.get('items', []):
            x_start = pdf.get_x()
            pdf.cell(anchuras[0], 3, str(item.get('id', ''))[:20], 1, 0, 'C')
            pdf.cell(anchuras[1], 3, str(item.get('cantidad', '0'))[:6], 1, 0, 'C')
            pdf.cell(anchuras[2], 3, str(item.get('unidad', 'MTS'))[:4], 1, 0, 'C')
            x_desc = pdf.get_x()
            pdf.multi_cell(anchuras[3], 3, str(item.get('descripcion', '')), 0, 'C')
            y_desc = pdf.get_y()
            pdf.set_y(y_desc - 3)
            pdf.set_x(x_desc + anchuras[3])
            pdf.cell(anchuras[4], 3, str(item.get('precio_unitario', ''))[:5], 1, 0, 'C')
            pdf.cell(anchuras[5], 3, str(item.get('total', '')), 1, 1, 'C')
            pdf.set_x(x_start)
            pdf.ln(2)
        
        pdf.ln(2)
        
        # Totales
        pdf.set_font("Arial", '', 10)
        pdf.cell(50, 5, "OP. GRAVADA:", 0, 0)
        pdf.cell(30, 5, self.format_currency(self.data.get('total_venta', '0.00')), 0, 1, 'R')
        pdf.cell(50, 5, "IGV:", 0, 0)
        pdf.cell(30, 5, self.format_currency(self.data.get('total_igv', '0.00')), 0, 1, 'R')
        
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(50, 6, "TOTAL:", 0, 0)
        pdf.cell(30, 8, self.format_currency(self.data.get('total_pagar', '0.00')), 0, 1, 'R')
        
        pdf.ln(2)
        pdf.set_font("Arial", '', 10)
        monto_l = self.data.get('monto_letras', '')
        if monto_l:
            pdf.multi_cell(0, 4, f"SON: {monto_l}", 0) if len(monto_l) > 24 else \
                pdf.cell(0, 4, f"SON: {monto_l}", 0, 1)
        
        pdf.ln(2)
        
        # QR
        self._generate_qr(pdf)
        
        # Pie
        pdf.cell(0, 4, "Representación impresa del comprobante de pago", 0, 1, 'C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 4, "¡Gracias por su compra!", 0, 1, 'C')
        
        pdf.output(self.output_path)
        logger.info(f"PDF generado: {self.output_path}")
    



# ========== FLASK ROUTES ==========

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversor XML a PDF - ManchesterTex</title>
    <script>
    function downloadPDF(base64Data, filename) {
        var link = document.createElement('a');
        link.href = 'data:application/pdf;base64,' + base64Data;
        link.download = filename;
        link.click();
    }
    </script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { 
            color: white; 
            text-align: center; 
            margin-bottom: 10px;
            font-size: 2rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .subtitle {
            color: rgba(255,255,255,0.9);
            text-align: center;
            margin-bottom: 30px;
            font-size: 1rem;
        }
        .main-content {
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }
        .left-panel {
            flex: 1;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 20px;
            min-height: 600px;
        }
        .right-panel {
            width: 380px;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 25px;
        }
        .viewer-header {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .viewer-header .btn {
            flex: 1;
            padding: 10px;
            font-size: 0.85rem;
        }
        @media (max-width: 1024px) {
            .main-content {
                flex-direction: column-reverse;
            }
            .right-panel {
                width: 100%;
            }
            .left-panel {
                min-height: 500px;
            }
        }
        @media (max-width: 600px) {
            .container {
                padding: 10px;
            }
            h1 {
                font-size: 1.5rem;
            }
            .subtitle {
                font-size: 0.9rem;
            }
            .right-panel, .left-panel {
                padding: 15px;
                min-height: auto;
            }
            #pdf-viewer {
                height: 400px;
            }
            .viewer-header {
                flex-direction: column;
            }
            .viewer-header .btn {
                width: 100%;
            }
            .info p {
                font-size: 0.8rem;
            }
            .btn-group {
                flex-direction: column;
            }
        }
        .form-group { margin-bottom: 20px; }
        label { 
            display: block; 
            margin-bottom: 8px; 
            font-weight: 600; 
            color: #374151;
            font-size: 0.95rem;
        }
        .file-input-wrapper {
            position: relative;
        }
        .file-name {
            display: block;
            padding: 12px 15px;
            background: #f0fdf4;
            border: 2px solid #22c55e;
            border-radius: 10px;
            color: #166534;
            font-weight: 500;
            margin-bottom: 10px;
        }
        .file-name.empty {
            background: #f8fafc;
            border: 2px dashed #cbd5e1;
            color: #9ca3af;
        }
        .file-input {
            display: block;
            width: 100%;
            padding: 15px;
            border: 2px dashed #cbd5e1;
            border-radius: 10px;
            background: #f8fafc;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
            color: #64748b;
            font-size: 0.9rem;
        }
        .file-input:hover {
            border-color: #667eea;
            background: #f1f5f9;
        }
        .file-input.has-file {
            border-color: #22c55e;
            background: #f0fdf4;
            color: #166534;
        }
        input[type="file"] {
            display: none;
        }
        .file-label {
            display: block;
            padding: 15px;
            border: 2px dashed #cbd5e1;
            border-radius: 10px;
            background: #f8fafc;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
            color: #64748b;
            font-size: 0.9rem;
        }
        .file-label:hover {
            border-color: #667eea;
            background: #f1f5f9;
        }
        .file-label.active {
            border-color: #22c55e;
            background: #f0fdf4;
            color: #166534;
        }
        .file-container {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
        }
        .file-container .file-name {
            flex: 1;
            padding: 12px 15px;
            background: #f0fdf4;
            border: 2px solid #22c55e;
            border-radius: 10px;
            color: #166534;
            font-weight: 500;
            word-break: break-all;
        }
        .file-x-btn {
            padding: 8px 12px;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
        }
        .file-x-btn:hover {
            background: #dc2626;
        }
        select { 
            width: 100%; 
            padding: 15px; 
            border-radius: 10px; 
            border: 1px solid #cbd5e1;
            background: white;
            font-size: 1rem;
        }
        .btn { 
            width: 100%; 
            padding: 15px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            border: none; 
            border-radius: 10px; 
            font-size: 1rem; 
            font-weight: 600; 
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover { 
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            background: #9ca3af;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        .btn-convert { margin-top: 10px; }
        .btn-download { 
            background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        }
        .btn-clean { 
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        }
        .btn-group {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        .btn-group .btn {
            flex: 1;
            padding: 12px;
            font-size: 0.9rem;
        }
        #pdf-viewer {
            width: 100%;
            height: 550px;
            border-radius: 8px;
            overflow: hidden;
        }
        .info { 
            margin-top: 20px; 
            padding: 20px; 
            background: #f0fdf4; 
            border-radius: 10px;
            border-left: 4px solid #22c55e;
        }
        .info h3 { color: #16a34a; margin-bottom: 12px; font-size: 1rem; }
        .info p { color: #166534; margin-bottom: 6px; line-height: 1.5; font-size: 0.9rem; }
        .info strong { display: inline-block; width: 80px; }
        .error { 
            background: #fef2f2; 
            color: #dc2626; 
            padding: 15px; 
            border-radius: 10px;
            border-left: 4px solid #dc2626;
            margin-top: 15px;
            font-size: 0.9rem;
        }
        .empty-state {
            text-align: center;
            color: #9ca3af;
            padding: 120px 20px;
        }
        .empty-state h2 { margin-bottom: 10px; color: #6b7280; }
        .footer {
            text-align: center;
            color: rgba(255,255,255,0.7);
            margin-top: 30px;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧾 Conversor XML a PDF</h1>
        <p class="subtitle">ManchesterTex E.I.R.L. - Facturación Electrónica</p>
        
        <div class="main-content">
            <div class="right-panel">
                <form id="convertirForm" method="POST" action="/convertir" enctype="multipart/form-data">
                    <div class="form-group">
                        <label>📤 Seleccionar archivo XML:</label>
                        <label for="xml_file" class="file-label" id="fileLabel">
                            Haz clic para seleccionar archivo (XML o CSV)
                        </label>
                        <input type="file" name="xml_file" id="xml_file" accept=".xml,.csv" required onchange="updateFileName()">
                        <div class="file-container" id="fileContainer" {% if not xml_file_name %}style="display: none;"{% endif %}>
                            <div class="file-name" id="fileName">{% if xml_file_name %}{{xml_file_name}}{% else %}Ningún archivo seleccionado{% endif %}</div>
                            <button type="button" class="file-x-btn" id="fileXBtn" onclick="removeFile()">✕</button>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="formato">📋 Formato de salida:</label>
                        <select name="formato" id="formato" onchange="checkFormato()">
                            <option value="ticket">Ticket 80mm</option>
                            <option value="yapes">YAPES Resumen</option>
                            <option value="shipping_label">Etiqueta de Envío</option>
                        </select>
                    </div>
                    
                    <button type="submit" class="btn btn-convert" id="convertirBtn" disabled>🔄 Convertir a PDF</button>
                {% if pdf_url %}
                <div class="viewer-header">
                    <a href="/download" class="btn btn-download">📥 Descargar PDF</a>
                    <a href="/clear" class="btn btn-clean">🗑️ Limpiar</a>
                </div>
                {% endif %}
            </div>
            
            <div class="left-panel">
                {% if pdf_url %}
                <iframe id="pdf-viewer" src="{{pdf_url}}" style="width:100%;height:600px;border:none;border-radius:8px;"></iframe>
                {% else %}
                <div class="empty-state">
                    <h2>📄 Esperando documento</h2>
                    <p>Sube un archivo XML para previsualizar el PDF</p>
                </div>
                {% endif %}
                
                {% if info %}
                <div class="info">
                    <h3>📄 Información del Documento</h3>
                    <p><strong>Tipo:</strong> {{ info.tipo }}</p>
                    <p><strong>Número:</strong> {{ info.numero }}</p>
                    <p><strong>Emisor:</strong> {{ info.emisor }}</p>
                    <p><strong>Cliente:</strong> {{ info.cliente }}</p>
                    <p><strong>Total:</strong> {{ info.total }}</p>
                    <p><strong>Fecha:</strong> {{ info.fecha }}</p>
                </div>
                {% endif %}
            </div>
        </div>
        
        <p class="footer">
            Sistema desarrollado por ManchesterTex E.I.R.L.<br>
            © 2026 Todos los derechos reservados
        </p>
    </div>
    
    <script>
    function updateFileName() {
        var input = document.getElementById('xml_file');
        var fileName = document.getElementById('fileName');
        var fileLabel = document.getElementById('fileLabel');
        var fileContainer = document.getElementById('fileContainer');
        var convertirBtn = document.getElementById('convertirBtn');
        
        if (input.files && input.files[0]) {
            var name = input.files[0].name;
            fileName.textContent = name;
            fileLabel.style.display = 'none';
            fileContainer.style.display = 'flex';
            convertirBtn.disabled = false;
        }
    }
    
    function checkFormato() {
        var convertirBtn = document.getElementById('convertirBtn');
        var input = document.getElementById('xml_file');
        if (input.files && input.files[0]) {
            convertirBtn.disabled = false;
        }
    }
    
    function removeFile() {
        var input = document.getElementById('xml_file');
        var fileName = document.getElementById('fileName');
        var fileLabel = document.getElementById('fileLabel');
        var fileContainer = document.getElementById('fileContainer');
        var convertirBtn = document.getElementById('convertirBtn');
        
        input.value = '';
        fileName.textContent = 'Ningún archivo seleccionado';
        fileLabel.style.display = 'block';
        fileContainer.style.display = 'none';
        convertirBtn.disabled = true;
    }
    
    // On page load, mantener archivo si existe
    {% if xml_file_name %}
    document.addEventListener('DOMContentLoaded', function() {
        var fileLabel = document.getElementById('fileLabel');
        var fileContainer = document.getElementById('fileContainer');
        var fileName = document.getElementById('fileName');
        fileLabel.style.display = 'none';
        fileContainer.style.display = 'flex';
    });
    {% endif %}
    </script>
</body>
</html>
"""


@app.route('/')
@log_request
def index():
    """Página principal"""
    # Verificar si hay un PDF en sesión
    temp_id = session.get('current_pdf')
    pdf_url = None
    info = None
    pdf_name = None
    xml_file_name = None
    
    if temp_id:
        pdf_path = session.get(f'pdf_{temp_id}')
        if pdf_path and os.path.exists(pdf_path):
            pdf_url = url_for('view_pdf', temp_id=temp_id)
            info = session.get('pdf_info')
            pdf_name = session.get('pdf_name')
            xml_file_name = session.get('xml_file_name')
    
    return render_template_string(HTML_TEMPLATE, pdf_url=pdf_url, info=info, pdf_name=pdf_name, xml_file_name=xml_file_name)


@app.route('/convertir', methods=['POST'])
@log_request
def convertir():
    """Endpoint para convertir XML/CSV a PDF"""
    try:
        # Validar archivo
        xml_file = request.files.get('xml_file')
        if not xml_file or xml_file.filename == '':
            return render_template_string(HTML_TEMPLATE, error="❌ Por favor, selecciona un archivo")
        
        filename = xml_file.filename.lower()
        formato = request.form.get('formato', CONFIG['DEFAULT_FORMAT'])
        
        # Determinar tipo de archivo
        if filename.endswith('.csv') or formato == 'yapes':
            if not filename.endswith('.csv'):
                return render_template_string(HTML_TEMPLATE, error="❌ Para formato YAPES debe subir un archivo CSV")
            
            # Procesar CSV para YAPES
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_csv:
                xml_file.save(tmp_csv.name)
                csv_path = tmp_csv.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='_yapes.pdf') as tmp_pdf:
                output_path = tmp_pdf.name
            
            yapes = YapesPDF(csv_path, output_path)
            
            if not yapes.parse_csv():
                return render_template_string(HTML_TEMPLATE, error="❌ Error al procesar el CSV. Formato: Nombre,Monto,Fecha")
            
            yapes.generate_pdf()
            
            # Nombre del archivo PDF
            fecha = datetime.now().strftime('%Y%m%d')
            pdf_name = f"YAPES_RESUMEN_{fecha}.pdf"
            
            info = {
                'tipo': 'YAPES RESUMEN',
                'numero': f"{len(yapes.data)} registros",
                'emisor': '-',
                'cliente': 'Varios',
                'total': '-',
                'fecha': datetime.now().strftime('%d/%m/%Y')
            }
            
        elif filename.endswith('.xml'):
            # Procesar XML para Ticket
            if not filename.endswith('.xml'):
                return render_template_string(HTML_TEMPLATE, error="❌ El archivo debe ser de tipo XML (.xml)")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp_xml:
                xml_file.save(tmp_xml.name)
                xml_path = tmp_xml.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='_ticket.pdf') as tmp_pdf:
                output_path = tmp_pdf.name
            
            factura = FacturaXMLtoPDF(xml_path, output_path)
            
            if not factura.parse_xml():
                error_msg = factura.errors[0] if factura.errors else "Error al procesar el XML"
                return render_template_string(HTML_TEMPLATE, error=f"❌ {error_msg}")
                        
            factura.generate_pdf(formato)

            # Nombre del archivo PDF: NUMERO_NOMBRE_CLIENTE_TIPO_FORMATO.pdf
            numero = factura.data.get('numero_factura', 'documento')
            cliente_nombre = factura.data.get('cliente_nombre', 'cliente').replace(' ', '_')
            cliente_nombre = ''.join(c for c in cliente_nombre if c.isalnum() or c == '_')
            pdf_name = f"{numero}_{cliente_nombre}_{formato}.pdf"
            
            info = {
                'tipo': factura.data.get('tipo_documento', 'N/A'),
                'numero': numero,
                'emisor': factura.data.get('emisor_nombre', 'N/A'),
                'cliente': factura.data.get('cliente_nombre', 'N/A'),
                'total': factura.format_currency(factura.data.get('total_pagar', '0.00')),
                'fecha': factura.data.get('fecha_emision', 'N/A')
            }
        else:
            return render_template_string(HTML_TEMPLATE, error="❌ Formato no soportado. Use XML o CSV")
        
        # Guardar PDF en archivo temporal y registrar en sesión
        temp_id = str(uuid.uuid4())
        session[f'pdf_{temp_id}'] = output_path
        session['current_pdf'] = temp_id
        session['pdf_name'] = pdf_name
        session['pdf_info'] = info
        session['xml_file_name'] = xml_file.filename  # Mantener nombre del archivo
        
        # Retornar con vista previa
        return render_template_string(HTML_TEMPLATE, pdf_url=url_for('view_pdf', temp_id=temp_id), info=info, pdf_name=pdf_name, xml_file_name=xml_file.filename)
        
    except Exception as e:
        logger.exception("Error en conversión")
        return render_template_string(HTML_TEMPLATE, error=f"❌ Error: {str(e)}")


@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok', 'service': 'XML to PDF Converter'})


@app.route('/pdf/<temp_id>')
def view_pdf(temp_id):
    """Servir PDF generado"""
    try:
        pdf_path = session.get(f'pdf_{temp_id}')
        if not pdf_path or not os.path.exists(pdf_path):
            return "PDF no encontrado", 404
        
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=False)
    except Exception as e:
        logger.exception("Error sirviendo PDF")
        return str(e), 500


@app.route('/download')
def download_pdf():
    """Descargar PDF"""
    try:
        temp_id = session.get('current_pdf')
        pdf_path = session.get(f'pdf_{temp_id}')
        pdf_name = session.get('pdf_name', 'documento.pdf')
        
        if not pdf_path or not os.path.exists(pdf_path):
            return "PDF no encontrado", 404
        
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=pdf_name)
    except Exception as e:
        logger.exception("Error descargando PDF")
        return str(e), 500


@app.route('/clear')
def clear_session():
    """Limpiar sesión y archivos temporales"""
    try:
        # Limpiar archivos temporales
        temp_id = session.get('current_pdf')
        if temp_id:
            pdf_path = session.get(f'pdf_{temp_id}')
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.unlink(pdf_path)
                except:
                    pass
            # Limpiar claves de sesión
            session.pop(f'pdf_{temp_id}', None)
        
        session.pop('current_pdf', None)
        session.pop('pdf_name', None)
        session.pop('pdf_info', None)
        
        return redirect(url_for('index'))
    except Exception as e:
        logger.exception("Error limpiando sesión")
        return redirect(url_for('index'))


# ========== MAIN ==========
if __name__ == '__main__':
    os.makedirs("images", exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)