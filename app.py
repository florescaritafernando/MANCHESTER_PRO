import xml.etree.ElementTree as ET
from fpdf import FPDF
import os
import tempfile
from typing import Tuple, Dict, Any
import base64
from datetime import datetime
import qrcode
from flask import Flask, request, send_file, render_template_string, jsonify
import io

app = Flask(__name__)

class FacturaXMLtoPDF:
    def __init__(self, xml_path, output_path, extra_data: Dict[str, Any] = None):
        self.xml_path = xml_path
        self.output_path = output_path
        self.data = {}
        self.line_height = 1
        self.page_width = 80 
        self.extra_data = extra_data if extra_data is not None else {} 

    def parse_xml(self):
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
                        
            namespaces = {
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
                'ds': 'http://www.w3.org/2000/09/xmldsig#'
            }
            
            self.data['monto_letras'] = ''
            self.data['forma_pago'] = ''
            self.data['otras_notes'] = []
            
            notes = root.findall('.//cbc:Note', namespaces)
            for note in notes:
                note_text = note.text or ''
                language_locale = note.get('languageLocaleID')
                language_id = note.get('languageID')
                                
                if language_locale == "1000":
                    self.data['monto_letras'] = note_text
                elif language_id == "L":
                    self.data['forma_pago'] = note_text
                else:
                    self.data['otras_notes'].append({
                        'texto': note_text,
                        'languageLocaleID': language_locale,
                        'languageID': language_id
                    })
                    
            self.data['numero_factura'] = self.get_text(root, './/cbc:ID', namespaces)
            self.data['fecha_emision'] = self.get_text(root, './/cbc:IssueDate', namespaces)
            self.data['hora_emision'] = self.get_text(root, './/cbc:IssueTime', namespaces)
                        
            numero = self.data.get('numero_factura', '')
            if numero and numero[0].upper() == 'F':
                self.data['tipo_documento'] = "FACTURA"
            else:
                self.data['tipo_documento'] = "BOLETA DE VENTA"
                        
            emisor = root.find('.//cac:AccountingSupplierParty/cac:Party', namespaces)
            if emisor is not None:               
                self.data['emisor_nombre'] = self.get_text(emisor, './/cbc:Name', namespaces) or self.get_text(emisor, './/cbc:RegistrationName', namespaces)
                self.data['emisor_ruc'] = self.get_text(emisor, './/cac:PartyIdentification/cbc:ID', namespaces) or self.get_text(emisor, './/cbc:ID', namespaces)
                self.data['emisor_direccion'] = self.get_text(emisor, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['emisor_distrito'] = self.get_text(emisor, './/cbc:District', namespaces)
                self.data['emisor_departamento'] = self.get_text(emisor, './/cbc:CityName', namespaces)
                self.data['correo_emisor'] = self.get_text(emisor, './/cbc:ElectronicMail', namespaces)
                        
            cliente = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces)
            if cliente is not None:
                self.data['cliente_nombre'] = self.get_text(cliente, './/cbc:RegistrationName', namespaces)
                self.data['cliente_ID'] = self.get_text(cliente, './/cac:PartyIdentification/cbc:ID', namespaces) or self.get_text(cliente, './/cbc:ID', namespaces) 
                self.data['cliente_direccion'] = self.get_text(cliente, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['cliente_distrito'] = self.get_text(cliente, './/cbc:District', namespaces)
                self.data['cliente_provincia'] = self.get_text(cliente, './/cbc:CountrySubentity', namespaces)
                self.data['cliente_departamento'] = self.get_text(cliente, './/cbc:CityName', namespaces)
                
            self.data['cliente_guia'] = self.get_text(root, './/cac:DespatchDocumentReference/cbc:ID', namespaces)
                        
            self.data['total_venta'] = self.get_text(root, './/cac:TaxSubtotal/cbc:TaxableAmount', namespaces, '0.0')
            self.data['total_igv'] = self.get_text(root, './/cac:TaxTotal/cbc:TaxAmount', namespaces, '0.0')
            self.data['total_pagar'] = self.get_text(root, './/cac:LegalMonetaryTotal/cbc:PayableAmount', namespaces, '0.0')
                        
            self.data['items'] = []
            for item in root.findall('.//cac:InvoiceLine', namespaces):
                item_data = {}
                item_data['id'] = self.get_text(item, './/cac:SellersItemIdentification/cbc:ID', namespaces)
                item_data['unidad'] = self.get_text(item, './/cbc:Note', namespaces)
                item_data['descripcion'] = self.get_text(item, './/cbc:Description', namespaces)
                item_data['cantidad'] = self.get_text(item, './/cbc:InvoicedQuantity', namespaces, '0')
                item_data['precio_unitario'] = self.get_text(item, './/cac:Price/cbc:PriceAmount', namespaces, '0.00')
                item_data['total'] = self.get_text(item, './/cbc:LineExtensionAmount', namespaces, '0.00')                              
                self.data['items'].append(item_data)
            
            self.data['tipo_codigo_invoice'] = self.get_text(root, './/cbc:InvoiceTypeCode', namespaces)
            self.data['tipo_doc_cli'] = self.get_text(root, './/cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID', namespaces, attr='schemeID')
            self.data['digest_value'] = self.get_text(root, './/ds:DigestValue', namespaces)

            namespaces_ds = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
            digest_node = root.find('.//ds:DigestValue', namespaces_ds)
            self.data['digest_value'] = digest_node.text if digest_node is not None else ""

            self.data.update(self.extra_data)
            
            return True
                    
        except Exception as e:
            print(f"Error al parsear XML: {e}")
            return False
    
    def get_text(self, node, path, namespaces, default='-', attr=None):
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

    def format_currency(self, amount):
        try:
            return f"S/. {float(amount):.2f}"
        except:
            return f"S/. 0.00"

    def calculate_total_height(self):
        pdf_temp = FPDF(orientation='P', unit='mm', format=(self.page_width, 300))
        pdf_temp.set_margins(left=0, top=0, right=0)
        pdf_temp.add_page()
        pdf_temp.set_font("Arial", '', 10)
        
        y = 2
        
        if os.path.exists("images/logo_manchester.png"):
            y += float(40) / 3 + 6
        
        y += 4
        
        emisor_nombre = self.data.get('emisor_nombre', 'N/A')
        if len(emisor_nombre) > 35:
            y += 8
        else:
            y += 4
        
        y += 4
        
        emisor_dir = self.data.get('emisor_direccion', '')
        emisor_dis = self.data.get('emisor_distrito', '')
        emisor_dep = self.data.get('emisor_departamento', '')
        direccion_completa = f"{emisor_dir}"
        if emisor_dis:
            direccion_completa += f" - {emisor_dis}"
        if emisor_dep:
            direccion_completa += f" - {emisor_dep}"
        
        if len(direccion_completa) > 35:
            y += 8
        else:
            y += 4
        
        y += 4
        y += 1 + 2
        y += 4
        y += 5
        y += 1 + 2
        y += 4
        y += 4
        y += 1 + 2
        y += 4
        y += 1 + 2
        
        cliente_nombre = self.data.get('cliente_nombre', 'N/A').upper()
        if len(cliente_nombre) > 25:
            y += 8
        else:
            y += 4
        
        y += 1
        
        c_dir = (self.data.get('cliente_direccion', '') or "").strip()
        c_dis = self.data.get('cliente_distrito', '')
        c_pro = self.data.get('cliente_provincia', '')
        c_dep = self.data.get('cliente_departamento', '')
        
        if len(c_dir) > 24:
            y += 8
        else:
            y += 4
        
        extras = [parte for parte in [c_dep, c_pro, c_dis] if parte and parte.strip()]
        if extras:
            y += 1
            if len(" - ".join(extras)) > 24:
                y += 8
            else:
                y += 4
        
        y += 2 + 1 + 2
        y += 4
        
        guia = self.data.get('cliente_guia', '')
        if guia and guia not in [None, '', 'N/A', '-']:
            y += 1
        
        f_pago = self.data.get('forma_pago', '')
        if f_pago:
            y += 1
        
        y += 1
        
        y += 2 + 1 + 2
        
        y += 1 + 2
        
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
        
        monto_l = self.data.get('monto_letras', '')
        if monto_l:
            if len(monto_l) > 24:
                y += 8
            else:
                y += 4
        
        y += 2
        
        y += float(30) / 3 + 20 + 4 + 4
        
        y += 20
        
        return max(100, min(800, y + 30))

    def generate_pdf(self, output_format: str = 'ticket'):
        if output_format == 'ticket':
            self._generate_ticket_pdf()
        else:
            raise ValueError("Formato de salida no válido.")

    def _generate_ticket_pdf(self):
        page_height = self.calculate_total_height()
        pdf = FPDF(orientation='P', unit='mm', format=(self.page_width, page_height))
        pdf.set_margins(left=0, top=0, right=0)
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        
        image_path = "images/logo_manchester.png"
        image_x = 20
        image_width = 40
        
        try:
            if os.path.exists(image_path):
                pdf.image(image_path, x=image_x, y=3, w=image_width)
                image_height = float(image_width) / 3
                pdf.ln(image_height + 4)
            else:
                os.makedirs("images", exist_ok=True)
                pdf.ln(5)
        except Exception as e:
            pdf.ln(5)
        
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)
        emisor_nombre = self.data.get('emisor_nombre', 'N/A')
        if len(emisor_nombre) > 35:
            pdf.multi_cell(0, 4, emisor_nombre, 0, 'C')
        else:
            pdf.cell(0, 4, emisor_nombre, 0, 1, 'C')
        
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 4, f"RUC: {self.data.get('emisor_ruc', 'N/A')}", 0, 1, 'C')

        emisor_dir = self.data.get('emisor_direccion', '')
        emisor_dis = self.data.get('emisor_distrito', '')
        emisor_dep = self.data.get('emisor_departamento', '')
        direccion_completa = f"{emisor_dir}"
        if emisor_dis:
            direccion_completa += f" - {emisor_dis}"
        if emisor_dep:
            direccion_completa += f" - {emisor_dep}"
            
        if len(direccion_completa) > 35:
            pdf.multi_cell(0, 4, direccion_completa, 0, 'C')
        else:
            pdf.cell(0, 4, direccion_completa, 0, 1, 'C')
        
        pdf.ln(1)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 4, f"{self.data.get('tipo_documento', 'COMPROBANTE')} ELECTRÓNICA", 0, 1, 'C')
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 5, self.data.get('numero_factura', 'N/A'), 0, 1, 'C')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        pdf.set_font("Arial", '', 10)
        cliente_id = self.data.get('cliente_ID', '')
        if len(cliente_id) == 11:
            pdf.cell(10, 4, f"RUC: ", 0, 0)
        elif len(cliente_id) == 8:
            pdf.cell(10, 4, f"DNI: ", 0, 0)
        elif cliente_id:
            pdf.cell(10, 4, f"CE: ", 0, 0)

        pdf.set_font("Arial", '', 12)
        pdf.cell(80, 4, cliente_id, 0, 1)

        pdf.ln(1)
        pdf.set_font("Arial", '', 10)
        cliente_nombre = self.data.get('cliente_nombre', 'N/A').upper()
        if len(cliente_nombre) > 25:
            pdf.multi_cell(0, 4, f"CLIENTE: {cliente_nombre}", 0)
        else:
            pdf.cell(0, 4, f"CLIENTE: {cliente_nombre}", 0, 1)
            
        pdf.ln(1)

        cliente_dir = self.data.get('cliente_direccion', '')
        cliente_dis = self.data.get('cliente_distrito', '')
        cliente_pro = self.data.get('cliente_provincia', '')
        cliente_dep = self.data.get('cliente_departamento', '')
        valores_invalidos = ['', 'N/A', 'n/a', '-', '--', '---', None]
        
        c_dir = (cliente_dir or "").strip()
        c_dis = (cliente_dis or "").strip()
        c_pro = (cliente_pro or "").strip()
        c_dep = (cliente_dep or "").strip()
                        
        pdf.set_font("Arial", '', 10)

        if len(c_dir) > 24:
            pdf.multi_cell(0, 4, f"DIRECCIÓN: {c_dir.upper()}", 0)
        else:
            pdf.cell(0, 4, f"DIRECCIÓN: {c_dir.upper()}", 0, 1, 'L')

        extras = [parte for parte in [c_dep, c_pro, c_dis] if parte and parte not in valores_invalidos]
        if extras:
            pdf.ln(1)
            direccion_a_mostrar = " - ".join(extras).upper()
            texto_ciudad = f"CIUDAD: {direccion_a_mostrar}"
            
            if len(texto_ciudad) > 24:
                pdf.multi_cell(0, 4, texto_ciudad, 0, 'L')
            else:
                pdf.cell(0, 4, texto_ciudad, 0, 1, 'L')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        pdf.set_font("Arial", '', 10)
        guia = self.data.get('cliente_guia', '')
        if guia and guia not in [None, '', 'N/A', '-'] and guia.strip():
            pdf.set_font("Arial", '', 10)
            pdf.cell(35, 4, "GUIA DE REMISIÓN: ", 0, 0)
            
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(45, 4, f"N° {guia}", 0, 1)
            pdf.ln(1)
        
        pdf.set_font("Arial", '', 10)

        f_pago = self.data.get('forma_pago', '').upper()
        if len(f_pago) > 15:
            pdf.multi_cell(0, 4, f"FORMA DE PAGO: {f_pago}", 0)
        else:
            pdf.cell(0, 4, f"FORMA DE PAGO: {f_pago}", 0, 1)
            
        pdf.ln(1)
        fecha = self.data.get('fecha_emision', 'N/A')
        hora = self.data.get('hora_emision', 'N/A')

        fecha_formateada = fecha

        if fecha != 'N/A':
            try:
                objeto_fecha = datetime.strptime(fecha, '%Y-%m-%d')
                fecha_formateada = objeto_fecha.strftime('%d/%m/%Y')
                
            except ValueError:
                pass

        if fecha_formateada != 'N/A' and hora != 'N/A':
            fecha_hora = f"{fecha_formateada} {hora}"
            pdf.cell(0, 4, f"FECHA DE EMISIÓN: {fecha_hora}", 0, 1, 'L')
        elif fecha_formateada != 'N/A':
            pdf.cell(0, 4, f"FECHA: {fecha_formateada}", 0, 1, 'L')
            if hora != 'N/A':
                pdf.cell(0, 4, f"HORA: {hora}", 0, 1, 'R')
        else:
            pdf.cell(0, 4, f"FECHA: {fecha}", 0, 1, 'L')
            if hora != 'N/A':
                pdf.cell(0, 4, f"HORA: {hora}", 0, 1, 'R')    
                
        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)
        
        anchuras = [8, 14, 10, 22, 10, 16]
        original_color = pdf.draw_color
        pdf.set_draw_color(255, 255, 255)

        pdf.set_font("Arial", '', 7)

        x2_start = pdf.get_x()
        pdf.cell(anchuras[0], 1, "COD.", 1, 0, 'C')
        pdf.cell(anchuras[1], 1, "CANT.", 1, 0, 'C')
        pdf.cell(anchuras[2], 1, "UNID.", 1, 0, 'C')
        pdf.cell(anchuras[3], 1, "DESCRIPCION", 1, 0, 'C')
        pdf.cell(anchuras[4], 1, "V.UNIT.", 1, 0, 'C')
        pdf.cell(anchuras[5], 1, "V.VENTA", 1, 1, 'C')

        pdf.set_draw_color(original_color)

        pdf.set_xy(x2_start, pdf.get_y())

        pdf.ln(2)
        pdf.cell(0, 2, "", "T", 1)

        pdf.set_font("Arial", '', 8)
        
        pdf.set_draw_color(255, 255, 255)

        for item in self.data.get('items', []):
            codigo = str(item.get('id', 'N/A'))[:20]
            cantidad = str(item.get('cantidad', '0'))[:6]
            unidad = str(item.get('unidad', 'MTS'))[:4]
            descripcion = str(item.get('descripcion', 'N/A'))
            precio_unitario = str(item.get('precio_unitario', '0.00'))[:5]
            total = str(item.get('total', '0.00'))
                        
            x_start = pdf.get_x()
            y_start = pdf.get_y()

            pdf.set_font("Arial", '', 8)

            pdf.cell(anchuras[0], 3, codigo, 1, 0, 'C')
            pdf.set_font("Arial", '', 10)

            pdf.cell(anchuras[1], 3, cantidad, 1, 0, 'C')

            pdf.set_font("Arial", '', 8)

            pdf.cell(anchuras[2], 3, unidad, 1, 0, 'C')

            x_descripcion = pdf.get_x()

            pdf.multi_cell(anchuras[3], 3, descripcion, 0, 'C')
            y_final = pdf.get_y()
            
            altura_fila = y_final - y_start

            pdf.set_y(y_start)
            
            pdf.set_x(x_descripcion + anchuras[3]) 

            pdf.cell(anchuras[4], altura_fila, precio_unitario, 1, 0, 'C')
            pdf.cell(anchuras[5], altura_fila, total, 1, 1, 'C')
            pdf.set_xy(x_start, pdf.get_y())
            pdf.ln(2)

        pdf.set_draw_color(original_color)
        pdf.ln(2)
        
        pdf.set_margins(left=0, top=2, right=0)
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
        monto_l = self.data.get('monto_letras')
        if len(monto_l) > 24:
            pdf.multi_cell(0, 4, f"SON: {monto_l}", 0)
        else:
            pdf.cell(0, 4, f"SON: {monto_l}", 0, 1)
        pdf.ln(2)
        
        ruc_emisor = self.data.get('emisor_ruc', '')
        tipo_invoice = self.data.get('tipo_codigo_invoice', '01')
        full_id = self.data.get('numero_factura', '').split('-')
        serie = full_id[0]
        correlativo = full_id[1]

        val_igv = float(self.data.get('total_igv', '0.0'))
        val_total = float(self.data.get('total_pagar', '0.0'))

        igv = "{:.2f}".format(val_igv).rstrip('0').rstrip('.')
        if '.' not in igv: igv += '.0'

        total = "{:.2f}".format(val_total).rstrip('0').rstrip('.')
        if '.' not in total: total += '.0'

        fecha = self.data.get('fecha_emision', '')
        tipo_doc_cliente = self.data.get('tipo_doc_cli', '')
        ruc_cli = self.data.get('cliente_ID', '')
        digest = self.data.get('digest_value', '')

        cadena_qr = f"{ruc_emisor}|{tipo_invoice}|{serie}|{correlativo}|{igv}|{total}|{fecha}|{tipo_doc_cliente}|{ruc_cli}|{digest}|"
        
        qr_img = qrcode.make(cadena_qr)
        qr_path = "images/temp_qr_dinamico.png"
        qr_img.save(qr_path)                                

        ruc_emisor = self.data.get('emisor_ruc', '')
        if ruc_emisor and ruc_emisor != 'N/A':
            image_path = "images/temp_qr_dinamico.png"
            if not os.path.exists(image_path):
                image_path = f"images/{ruc_emisor}.png"
            
            image_width = 30
            image_x = (float(self.page_width) - float(image_width)) / 2
            try:
                if os.path.exists(image_path):
                    pdf.image(image_path, x=image_x, y=pdf.get_y(), w=image_width)
                    image_height = float(image_width) / 3
                    pdf.set_y(pdf.get_y() + image_height + 20)
            except Exception as e:
                pass
        
        pdf.cell(0, 4, "Representación impresa del comprobante de pago", 0, 1, 'C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 4, "¡Gracias por su compra!", 0, 1, 'C')
        
        pdf.output(self.output_path)
        print(f"PDF generado: {self.output_path} (Ticket 80mm)")


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversor XML a PDF - Ticket 80mm</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #2563eb; text-align: center; margin-bottom: 30px; }
        .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #374151; }
        input[type="file"] { width: 100%; padding: 12px; border: 2px dashed #e0e0e0; border-radius: 8px; }
        .btn { width: 100%; padding: 15px; background: #4CAF50; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 20px; }
        .btn:hover { background: #45a049; }
        .btn-secondary { background: #6b7280; margin-top: 10px; }
        .btn-secondary:hover { background: #5b5f6a; }
        .info { margin-top: 30px; padding: 20px; background: #f9fafb; border-radius: 8px; }
        .info h3 { color: #059669; margin-bottom: 15px; }
        .info p { margin-bottom: 8px; line-height: 1.6; }
        .error { background: #fee2e2; color: #dc2626; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .success { background: #d1fae5; color: #059669; padding: 15px; border-radius: 8px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧾 Conversor XML a PDF - Ticket 80mm</h1>
        <div class="card">
            <form method="POST" action="/convertir" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="xml_file">📤 Subir archivo XML:</label>
                    <input type="file" name="xml_file" id="xml_file" accept=".xml" required>
                </div>
                <div class="form-group">
                    <label for="formato">📋 Formato de salida:</label>
                    <select name="formato" id="formato" style="width:100%; padding:12px; border-radius:8px; border:1px solid #e0e0e0;">
                        <option value="ticket">Ticket 80mm</option>
                    </select>
                </div>
                <button type="submit" class="btn">🔄 Convertir a PDF</button>
            </form>
            
            {% if info %}
            <div class="info">
                <h3>📝 Información del documento</h3>
                <p>{{ info }}</p>
            </div>
            {% endif %}
            
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""


@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/convertir', methods=['POST'])
def convertir():
    try:
        xml_file = request.files.get('xml_file')
        formato = request.form.get('formato', 'ticket')
        
        if not xml_file or xml_file.filename == '':
            return render_template_string(HTML_TEMPLATE, error="❌ Por favor, sube un archivo XML")
        
        if not xml_file.filename.endswith('.xml'):
            return render_template_string(HTML_TEMPLATE, error="❌ El archivo debe ser XML")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp_xml:
            xml_file.save(tmp_xml.name)
            xml_path = tmp_xml.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='_ticket.pdf') as tmp_pdf:
            output_path = tmp_pdf.name
        
        factura = FacturaXMLtoPDF(xml_path, output_path)
        
        if factura.parse_xml():
            factura.generate_pdf(formato)
            
            info = f"""
✅ CONVERSIÓN EXITOSA

📄 Documento: {factura.data.get('tipo_documento', 'N/A')}
🔢 Número: {factura.data.get('numero_factura', 'N/A')}
🏢 Emisor: {factura.data.get('emisor_nombre', 'N/A')}
👤 Cliente: {factura.data.get('cliente_nombre', 'N/A')}
💰 Total: {factura.format_currency(factura.data.get('total_pagar', '0.00'))}
📅 Fecha: {factura.data.get('fecha_emision', 'N/A')}
            """
            
            return send_file(output_path, as_attachment=True, download_name=f"{factura.data.get('numero_factura', 'ticket')}.pdf")
        else:
            return render_template_string(HTML_TEMPLATE, error="❌ Error al procesar el XML")
            
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, error=f"❌ Error: {str(e)}")


if __name__ == '__main__':
    os.makedirs("images", exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)