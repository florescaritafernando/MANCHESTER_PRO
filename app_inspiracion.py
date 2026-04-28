import xml.etree.ElementTree as ET
from fpdf import FPDF
import os
import tempfile
from typing import Tuple, Dict, Any
import gradio as gr
import base64
from datetime import datetime
import qrcode
import urllib.parse

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
            
            # Inicializar datos
            self.data['monto_letras'] = ''
            self.data['forma_pago'] = ''
            self.data['otras_notes'] = []
            
            # Extraer todos los notes
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
                        
            # DETECTAR TIPO DE DOCUMENTO AUTOMÁTICAMENTE
            numero = self.data.get('numero_factura', '')
            if numero and numero[0].upper() == 'F':
                self.data['tipo_documento'] = "FACTURA"
            else:
                self.data['tipo_documento'] = "BOLETA DE VENTA"
                        
            # Datos del emisor
            emisor = root.find('.//cac:AccountingSupplierParty/cac:Party', namespaces)
            if emisor is not None:               
                self.data['emisor_nombre'] = self.get_text(emisor, './/cbc:Name', namespaces) or self.get_text(emisor, './/cbc:RegistrationName', namespaces)
                self.data['emisor_ruc'] = self.get_text(emisor, './/cac:PartyIdentification/cbc:ID', namespaces) or self.get_text(emisor, './/cbc:ID', namespaces)
                self.data['emisor_direccion'] = self.get_text(emisor, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['emisor_distrito'] = self.get_text(emisor, './/cbc:District', namespaces)
                self.data['emisor_departamento'] = self.get_text(emisor, './/cbc:CityName', namespaces)
                self.data['correo_emisor'] = self.get_text(emisor, './/cbc:ElectronicMail', namespaces)
                        
            # Datos del cliente
            cliente = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces)
            if cliente is not None:
                self.data['cliente_nombre'] = self.get_text(cliente, './/cbc:RegistrationName', namespaces)
                self.data['cliente_ID'] = self.get_text(cliente, './/cac:PartyIdentification/cbc:ID', namespaces) or self.get_text(cliente, './/cbc:ID', namespaces) 
                self.data['cliente_direccion'] = self.get_text(cliente, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['cliente_distrito'] = self.get_text(cliente, './/cbc:District', namespaces)
                self.data['cliente_provincia'] = self.get_text(cliente, './/cbc:CountrySubentity', namespaces)
                self.data['cliente_departamento'] = self.get_text(cliente, './/cbc:CityName', namespaces)
                
            self.data['cliente_guia'] = self.get_text(root, './/cac:DespatchDocumentReference/cbc:ID', namespaces)
                        
            # Totales
            self.data['total_venta'] = self.get_text(root, './/cac:TaxSubtotal/cbc:TaxableAmount', namespaces, '0.0')
            self.data['total_igv'] = self.get_text(root, './/cac:TaxTotal/cbc:TaxAmount', namespaces, '0.0')
            self.data['total_pagar'] = self.get_text(root, './/cac:LegalMonetaryTotal/cbc:PayableAmount', namespaces, '0.0')
                        
            # Items de la factura
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
            
            #guia de remision
            # Datos del emisor
            guia_emisor = root.find('.//cac:DespatchSupplierParty/cac:Party', namespaces)
            if guia_emisor is not None:
                self.data['guia_emisor_direccion'] = self.get_text(guia_emisor, './/cac:PostalAddress/cbc:StreetName', namespaces)
                self.data['guia_emisor_distrito'] = self.get_text(guia_emisor, './/cac:PostalAddress/cbc:District', namespaces)
                self.data['guia_emisor_departamento'] = self.get_text(guia_emisor, './/cac:PostalAddress/cbc:CityName', namespaces)
                self.data['guia_ruc_emisor'] = self.get_text(guia_emisor, './/cac:PartyIdentification/cbc:ID', namespaces)
                self.data['guia_razon_social_emisor'] = self.get_text(guia_emisor, './/cac:PartyLegalEntity/cbc:RegistrationName', namespaces)

            self.data['nro_guia_remision_electronica'] = self.get_text(root, './/cbc:ID', namespaces)

            #DATOS CLIENTE GUIA
            guia_cliente = root.find('.//cac:DeliveryCustomerParty/cac:Party', namespaces)
            if guia_cliente is not None:
                self.data['guia_cliente_nombre'] = self.get_text(guia_cliente, './/cac:PartyLegalEntity/cbc:RegistrationName', namespaces)
                self.data['guia_cliente_ID'] = self.get_text(guia_cliente, './/cac:PartyIdentification/cbc:ID', namespaces)
                self.data['guia_cliente_direccion'] = self.get_text(guia_cliente, './/cac:PostalAddress/cbc:StreetName', namespaces)
                self.data['guia_cliente_distrito'] = self.get_text(guia_cliente, './/cac:PostalAddress/cbc:District', namespaces)
                self.data['guia_cliente_departamento'] = self.get_text(guia_cliente, './/cac:PostalAddress/cbc:CityName', namespaces)

            # Documentos Relacionados
            self.data['doc_relacionado_nro'] = self.get_text(root, './/cac:AdditionalDocumentReference/cbc:ID', namespaces)
            self.data['doc_relacionado_tipo'] = self.get_text(root, './/cac:AdditionalDocumentReference/cbc:DocumentType', namespaces)
                
            guia_detalles = root.find('.//cac:Shipment', namespaces)
            if guia_detalles is not None:
                self.data['guia_tipo_transportista'] = self.get_text(guia_detalles, './/cac:ShipmentStage/cbc:TransportModeCode', namespaces)
                self.data['motivo_transportista'] = self.get_text(guia_detalles, './/cbc:HandlingCode', namespaces)
                self.data['fecha_guia'] = self.get_text(guia_detalles, './/cac:ShipmentStage/cac:TransitPeriod/cbc:StartDate', namespaces)
                self.data['peso_bruto'] = self.get_text(guia_detalles, './/cbc:GrossWeightMeasure', namespaces)
                self.data['nombre_transportista'] = self.get_text(guia_detalles, './/cac:CarrierParty/cac:PartyLegalEntity/cbc:RegistrationName', namespaces)
                self.data['ruc_transportista'] = self.get_text(guia_detalles, './/cac:CarrierParty/cac:PartyIdentification/cbc:ID', namespaces)

            delivery_guia_llegada = root.find('.//cac:Delivery/cac:DeliveryAddress', namespaces)
            if delivery_guia_llegada is not None:
                self.data['delivery_direccion_llegada'] = self.get_text(delivery_guia_llegada, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['delivery_departamento_llegada'] = self.get_text(delivery_guia_llegada, './/cbc:CityName', namespaces)
                self.data['delivery_cuidad_llegada'] = self.get_text(delivery_guia_llegada, './/cbc:CountrySubentity', namespaces)
                self.data['delivery_distrito_llegada'] = self.get_text(delivery_guia_llegada, './/cbc:District', namespaces)

            delivery_guia_partida = root.find('.//cac:Delivery/cac:Despatch/cac:DespatchAddress', namespaces)
            if delivery_guia_partida is not None:
                self.data['delivery_direccion_partida'] = self.get_text(delivery_guia_partida, './/cac:AddressLine/cbc:Line', namespaces)
                self.data['delivery_departamento_partida'] = self.get_text(delivery_guia_partida, './/cbc:CityName', namespaces)
                self.data['delivery_cuidad_partida'] = self.get_text(delivery_guia_partida, './/cbc:CountrySubentity', namespaces)
                self.data['delivery_distrito_partida'] = self.get_text(delivery_guia_partida, './/cbc:District', namespaces)           
             
            # Items de la guia
            self.data['items_DespatchLine'] = []
            for item in root.findall('.//cac:DespatchLine', namespaces):
                item_data = {}
                item_data['id'] = self.get_text(item, './/cbc:ID', namespaces)
                item_data['unidad'] = self.get_text(item, './/cbc:Note', namespaces)
                item_data['descripcion'] = self.get_text(item, './/cac:Item/cbc:Description', namespaces)
                item_data['cantidad'] = self.get_text(item, './/cbc:DeliveredQuantity', namespaces, '0')
                                
                self.data['items_DespatchLine'].append(item_data)

            #QR FACTURAS
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
            

    def extraer_hash_xml(self):
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
            namespaces = {
                'ds': 'http://www.w3.org/2000/09/xmldsig#'
            }
            self.data['hash_extraido'] = self.get_text(root, './/ds:DigestValue', namespaces)
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

    def calcular_lineas_texto(self, texto, ancho_maximo, font_size=6):
        if not texto:
            return 1
        caracteres_por_linea = int(ancho_maximo * 2.2)
        return max(1, (len(texto) // caracteres_por_linea) + 1)

    def calculate_total_height(self):
        pdf_temp = FPDF(orientation='P', unit='mm', format=(self.page_width, 300))
        pdf_temp.add_page()
        pdf_temp.set_font("Arial", '', 8)
        y_position = 2
        try:
            if os.path.exists("images/logo_manchester.png"):
                y_position += 25 + 2
        except:
            pass

        return 210

    def calculate_total_height_gre(self):
        pdf_temp = FPDF(orientation='P', unit='mm', format=(self.page_width, 300))
        pdf_temp.add_page()
        pdf_temp.set_font("Arial", '', 8)
        y_position = 2
        try:
            if os.path.exists("images/logo_manchester.png"):
                y_position += 25 + 2
        except:
            pass

        return 250
    
    def generar_url_qr_sunat(self):
        digest_original = self.data.get('digest_value', '') 
        digest_codificado = urllib.parse.quote(digest_original, safe='')
        url_base = "https://e-factura.sunat.gob.pe/v1/contribuyente/gre/comprobantes/descargaqr?hashqr="
        url_completa = f"{url_base}{digest_codificado}"
        return url_completa                                               

    def generate_pdf(self, output_format: str):
        if output_format == 'ticket':
            self._generate_ticket_pdf()
        elif output_format == 'etiqueta_envio':
            self._generate_shipping_label_pdf()
        elif output_format == 'etiqueta_envio_otro':
            self._generate_shipping_label_pdf_2()
        elif output_format == 'guia_de_remision':
            self._generate_gre_ticket_pdf()
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
                image_height = image_width / 3
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
        pdf.set_char_spacing(0.5)
        pdf.cell(0, 4, f"RUC: {self.data.get('emisor_ruc', 'N/A')}", 0, 1, 'C')
        pdf.set_char_spacing(0.0)

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
        pdf.set_char_spacing(1)
        pdf.cell(0, 5, self.data.get('numero_factura', 'N/A'), 0, 1, 'C')
        pdf.set_char_spacing(0.0)

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
        pdf.set_char_spacing(0.5)
        pdf.cell(80, 4, cliente_id, 0, 1)
        pdf.set_char_spacing(0.0)

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
            pdf.set_char_spacing(1)
            pdf.cell(45, 4, f"N° {guia}", 0, 1)
            pdf.set_char_spacing(0.0)
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

            pdf.set_char_spacing(1)
            pdf.cell(anchuras[1], 3, cantidad, 1, 0, 'C')
            pdf.set_char_spacing(0.0)

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
        pdf.set_char_spacing(1)
        pdf.cell(30, 8, self.format_currency(self.data.get('total_pagar', '0.00')), 0, 1, 'R')
        pdf.set_char_spacing(0.0)

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
            image_x = (self.page_width - image_width) / 2
            try:
                if os.path.exists(image_path):
                    pdf.image(image_path, x=image_x, y=pdf.get_y(), w=image_width)
                    image_height = image_width / 3
                    pdf.set_y(pdf.get_y() + image_height + 20)
            except Exception as e:
                pass
        
                
        pdf.cell(0, 4, "Representación impresa del comprobante de pago", 0, 1, 'C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 4, "¡Gracias por su compra!", 0, 1, 'C')
        
        pdf.output(self.output_path)
        print(f"PDF generado: {self.output_path} (Ticket 80mm)")
        
    def _generate_shipping_label_pdf(self):
        label_width = 100
        label_height = 150

        pdf = FPDF(orientation='P', unit='mm', format=(label_width, label_height))
        pdf.set_margins(left=5, top=5, right=5)
        pdf.add_page()
        pdf.set_auto_page_break(auto=False)
        
        emisor_nombre = self.data.get('emisor_nombre', 'N/A').upper()
        emisor_ruc = self.data.get('emisor_ruc', 'N/A')
        
        logo_path = "images/logo_manchester.png"
        logo_width = 35
        pdf.set_y(5)
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=5, y=5, w=logo_width) 
            pdf.set_y(25) 
        else:
            pdf.set_font("Arial", 'B', 14)
            pdf.set_xy(5, 5) 
            pdf.cell(35, 7, "MANCHESTER", 0, 0, 'L')
            pdf.set_y(15)

        remitente_x = label_width - 5 - 45
        pdf.set_y(5)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_xy(remitente_x, 5)
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

        pdf.line(5, pdf.get_y() + 1, label_width - 5, pdf.get_y() + 1) 
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

        y_qr_start = pdf.get_y()
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
            pdf.cell(qr_width, 5, "QR P-Holder", 0, 0, 'C')
            
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
        info_y = y_qr_start 
        
        pdf.set_xy(info_x, info_y)
        pdf.set_draw_color(0, 0, 0) 
        pdf.set_line_width(0.2)
        pdf.set_fill_color(255 , 255, 255)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_char_spacing(1)
        pdf.cell(info_width, 5, f"N° DE DOC.: {num_documento}", 1, 1, 'C', True)
        
        pdf.set_x(info_x)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(info_width, 5, f"FECHA DE EMISIÓN: {fecha_formateada}", 1, 1, 'C', True)

        if guia_remision != 'N/A' and guia_remision.strip():
            pdf.set_x(info_x)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(info_width, 5, f"GUÍA DE REMISIÓN: N° {guia_remision}", 1, 1, 'C', True)

        pdf.set_char_spacing(0)

        pdf.output(self.output_path)
        print(f"Etiqueta de envío generada: {self.output_path} (100mm x 150mm)") 

    def _generate_shipping_label_pdf_2(self):
        label_width = 100
        label_height = 150
        
        cliente_nombre_manual = self.extra_data.get('cliente_nombre_manual', 'N/A').upper()
        cliente_id_manual = self.extra_data.get('cliente_id_manual', 'N/A')
        direccion_envio_manual = self.extra_data.get('direccion_envio_manual', 'N/A').upper()
        agencia_manual = self.extra_data.get('agencia_manual', 'N/A').upper()
        otros_manual = self.extra_data.get('otros_manual', 'N/A').upper()
        
        pdf = FPDF(orientation='P', unit='mm', format=(label_width, label_height))
        pdf.set_margins(left=5, top=5, right=5)
        pdf.add_page()
        pdf.set_auto_page_break(auto=False)
        
        emisor_nombre = self.data.get('emisor_nombre', 'N/A').upper()
        emisor_ruc = self.data.get('emisor_ruc', 'N/A')
        
        logo_path = "images/logo_manchester.png"
        logo_width = 35
        pdf.set_y(5)
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=5, y=5, w=logo_width) 
            pdf.set_y(25) 
        else:
            pdf.set_font("Arial", 'B', 14)
            pdf.set_xy(5, 5) 
            pdf.cell(35, 7, "MANCHESTER", 0, 0, 'L')
            pdf.set_y(15)

        remitente_x = label_width - 5 - 45
        pdf.set_y(5)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_xy(remitente_x, 5)
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

        pdf.line(5, pdf.get_y() + 1, label_width - 5, pdf.get_y() + 1) 
        pdf.set_y(pdf.get_y() + 3) 

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 5, "DATOS DESTINATARIO", 0, 1, 'C') 

        pdf.set_font("Arial", 'B', 20)

        if pdf.get_string_width(cliente_nombre_manual) > 200:
            pdf.set_font("Arial", 'B', 15)
            pdf.multi_cell(90, 8, cliente_nombre_manual, 0, 'L')
        else:
            pdf.multi_cell(90, 8, cliente_nombre_manual, 0, 'L')

        pdf.ln(2)

        pdf.set_font("Arial", '', 15)
        pdf.set_char_spacing(0.5)
        id_label = "RUC" if len(cliente_id_manual) == 11 else ("DNI" if len(cliente_id_manual) == 8 else "CE")
        pdf.cell(90, 5, f"{id_label}: {cliente_id_manual}", 0, 1, 'L')
        pdf.set_char_spacing(0.0)
        pdf.ln(1)

        pdf.set_font("Arial", '', 8)

        pdf.cell(90, 6, "DIRECCIÓN DE ENVIO:", 0, 1, 'L')
        pdf.set_font("Arial", 'B', 15)
        pdf.ln(1)
        if pdf.get_string_width(direccion_envio_manual) > 200:
            pdf.set_font("Arial", 'B', 10)
            pdf.multi_cell(90, 5, direccion_envio_manual, 'B', 'L')
        else:
            pdf.multi_cell(90, 5, direccion_envio_manual, 'B', 'L')
        
        pdf.ln(3)
        
        if agencia_manual:
            ancho_label = 20 
            ancho_valor = 70 
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "AGENCIA:", 0, 0, 'L') 

            if pdf.get_string_width(agencia_manual) > 100:
                pdf.set_font("Arial", 'B', 8)
                pdf.multi_cell(ancho_valor, 4, agencia_manual, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, agencia_manual, 0, 'L')
            pdf.ln(1) 
        pdf.ln(2)
        if otros_manual:

            ancho_label = 15
            ancho_valor = 75

            pdf.set_font("Arial", 'B', 10)
            pdf.cell(ancho_label, 4, "OTROS:", 0, 0, 'L') 

            pdf.set_font("Arial", '', 10)                                               

            if pdf.get_string_width(otros_manual) > 100:
                pdf.set_font("Arial", '', 8)
                pdf.multi_cell(ancho_valor, 4, otros_manual, 0, 'L')
            else:
                pdf.multi_cell(ancho_valor, 4, otros_manual, 0, 'L')
            pdf.ln(1) 

        y_qr_start = pdf.get_y()
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
            pdf.cell(qr_width, 5, "QR P-Holder", 0, 0, 'C')
            
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
        info_y = y_qr_start 
        
        pdf.set_xy(info_x, info_y)
        pdf.set_draw_color(0, 0, 0) 
        pdf.set_line_width(0.2)
        pdf.set_fill_color(255 , 255, 255)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_char_spacing(1)
        pdf.cell(info_width, 5, f"N° DE DOC.: {num_documento}", 1, 1, 'C', True)
        
        pdf.set_x(info_x)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(info_width, 5, f"FECHA DE EMISIÓN: {fecha_formateada}", 1, 1, 'C', True)

        if guia_remision != 'N/A' and guia_remision.strip():
            pdf.set_x(info_x)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(info_width, 5, f"GUÍA DE REMISIÓN: N° {guia_remision}", 1, 1, 'C', True)

        pdf.set_char_spacing(0)

        pdf.output(self.output_path)
        print(f"Etiqueta de envío generada: {self.output_path} (100mm x 150mm) Recoge otra persona") 


    def _generate_gre_ticket_pdf(self):
        page_height = self.calculate_total_height_gre()
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
                image_height = image_width / 3
                pdf.ln(image_height + 4)
            else:
                os.makedirs("images", exist_ok=True)
                pdf.ln(5)
        except Exception as e:
            pdf.ln(5)
        
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)
        guia_emisor_nombre = self.data.get('guia_razon_social_emisor', 'N/A')
        if len(guia_emisor_nombre) > 35:
            pdf.multi_cell(0, 4, guia_emisor_nombre, 0, 'C')
        else:
            pdf.cell(0, 4, guia_emisor_nombre, 0, 1, 'C')
        
        pdf.set_font("Arial", '', 10)
        pdf.set_char_spacing(0.5)
        pdf.cell(0, 4, f"RUC: {self.data.get('guia_ruc_emisor', 'N/A')}", 0, 1, 'C')
        pdf.set_char_spacing(0.0)

        emisor_dir = self.data.get('guia_emisor_direccion', '')
        emisor_dis = self.data.get('guia_emisor_distrito', '')
        emisor_dep = self.data.get('guia_emisor_departamento', '')
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
        pdf.multi_cell(0, 4, "GUÍA DE REMISIÓN REMITENTE ELECTRÓNICA", 0, "C")
        
        pdf.ln(1)
        pdf.set_font("Arial", 'B', 14)
        pdf.set_char_spacing(1)
        pdf.cell(0, 5, self.data.get('nro_guia_remision_electronica', 'N/A'), 0, 1, 'C')
        pdf.set_char_spacing(0.0)

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "DATOS DESTINATARIO", 0, 1, "C")
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)
        cliente_id = self.data.get('guia_cliente_ID', '')
        if len(cliente_id) == 11:
            pdf.cell(10, 4, f"RUC: ", 0, 0)
        elif len(cliente_id) == 8:
            pdf.cell(10, 4, f"DNI: ", 0, 0)
        elif cliente_id:
            pdf.cell(10, 4, f"CE: ", 0, 0)

        pdf.set_font("Arial", '', 12)
        pdf.set_char_spacing(0.5)
        pdf.cell(80, 4, cliente_id, 0, 1)
        pdf.set_char_spacing(0.0)

        pdf.ln(1)
        pdf.set_font("Arial", '', 10)
        cliente_nombre = self.data.get('guia_cliente_nombre', 'N/A').upper()
        if len(cliente_nombre) > 25:
            pdf.multi_cell(0, 4, f"CLIENTE: {cliente_nombre}", 0)
        else:
            pdf.cell(0, 4, f"CLIENTE: {cliente_nombre}", 0, 1)
            
        pdf.ln(1)

        cliente_dir = self.data.get('guia_cliente_direccion', '')
        cliente_dis = self.data.get('guia_cliente_distrito', '')
        cliente_dep = self.data.get('guia_cliente_departamento', '')
        valores_invalidos = ['', 'N/A', 'n/a', '-', '--', '---']
        partes_validas = [parte for parte in [cliente_dir, cliente_dis, cliente_dep] 
                         if parte and parte not in valores_invalidos]
                         
        if partes_validas:
            direccion_completa = " - ".join(partes_validas).upper()
            texto_direccion = f"DIRECCIÓN: {direccion_completa}"
            if len(texto_direccion) > 24:
                pdf.multi_cell(0, 4, texto_direccion, 0)
            else:
                pdf.cell(0, 4, texto_direccion, 0, 1)

        pdf.ln(1)

        fecha = self.data.get('fecha_emision', '')

        if fecha and fecha != 'N/A':
            try:
                fecha_obj0 = datetime.strptime(fecha, '%Y-%m-%d')
                
                meses = {
                    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
                    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"
                }
                
                dia = fecha_obj0.strftime('%d') 
                mes = meses[fecha_obj0.month]  
                anio = fecha_obj0.year          
                
                self.data['fecha_guia_formateada2'] = f"{dia}-{mes}-{anio}"
                
            except Exception:
                self.data['fecha_guia_formateada2'] = fecha 
        else:
            self.data['fecha_guia_formateada2'] = 'N/A' 

        pdf.cell(0, 4, f"FECHA DE EMISION: {self.data.get('fecha_guia_formateada2', '-')}", 0, 1)

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "DOCUMENTOS RELACIONADOS", 0, 1, 'C')
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)

        doc_nro = self.data.get('doc_relacionado_nro', 'N/A')
        doc_tipo = self.data.get('doc_relacionado_tipo', 'N/A').upper()

        pdf.cell(0, 4, f"TIPO DE DOC.: {doc_tipo}", 0, 1, 'C')
        pdf.cell(0, 4, f"NRO. DE DOC.: {doc_nro}", 0, 1, 'C')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        #OBSERVACION (RECOGE OTRA PERSONA) ------ FALTA VER ESTO AUN NO LLEGA NINGUNA CON ESTE DATO
        

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "DETALLES DE LA GUIA", 0, 1, "C")

        pdf.ln(1)
        
        x_half = (self.page_width / 2)
        y_start_details = pdf.get_y()

        tip_tr = {"01": "PÚBLICO", "02": "PRIVADO"}.get(self.data.get('guia_tipo_transportista'), 'N/A')   
        mot = {"01": "VENTA", "02": "OTROS"}.get(self.data.get('motivo_transportista'), 'N/A')      
        peso = self.data.get('peso_bruto', 'N/A') 

        fecha_raw = self.data.get('fecha_guia', '')

        if fecha_raw and fecha_raw != 'N/A':
            try:
                fecha_obj = datetime.strptime(fecha_raw, '%Y-%m-%d')
                
                meses = {
                    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
                    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"
                }
                
                dia = fecha_obj.strftime('%d') 
                mes = meses[fecha_obj.month]  
                anio = fecha_obj.year          
                
                self.data['fecha_guia_formateada'] = f"{dia}-{mes}-{anio}"
                
            except Exception:
                self.data['fecha_guia_formateada'] = fecha_raw 
        else:
            self.data['fecha_guia_formateada'] = 'N/A'                                  

        m_left = 0

        pdf.set_font("Arial", '', 7)
        pdf.multi_cell(x_half - 4, 3, f"TIPO DE TRANSPORTISTA: {tip_tr}", 0, 'L')

        pdf.set_x(m_left)
        pdf.multi_cell(x_half - 4, 3, f"PESO BRUTO: {peso}", 0, 'L')

        pdf.set_x(m_left)
        pdf.multi_cell(x_half - 4, 3, f"MOTIVO: {mot}", 0, 'L')
        
        pdf.set_x(m_left)
        pdf.cell(0, 3, f"DESCRIPCION:", 0, 1)

        y_end_left = pdf.get_y()
        pdf.set_xy(x_half, y_start_details)
        
        pdf.cell(0, 3, "REGISTRO MTC:", 0, 1)

        pdf.set_x(x_half)
        pdf.set_font("Arial", '', 7)
        pdf.cell(0, 3, f"UND. DE MEDIDA: KGM", 0, 1)

        pdf.set_x(x_half)
        pdf.set_font("Arial", '', 7)
        pdf.multi_cell(x_half - 4, 3, f"F. ENTREGA DE BIENES AL TRANSPORTISTA: {self.data.get('fecha_guia_formateada', '-')}", 0, 'L')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        dir_ll = self.data.get('delivery_direccion_llegada', '-')
        dep_ll = self.data.get('delivery_departamento_llegada', '-')
        ciu_ll = self.data.get('delivery_cuidad_llegada', '-')
        dis_ll = self.data.get('delivery_distrito_llegada', '-')
        self.data['full_llegada'] = f"{dir_ll}, {dep_ll} - {ciu_ll} - {dis_ll}".upper()

        dir_pa = self.data.get('delivery_direccion_partida', '-')
        dep_pa = self.data.get('delivery_departamento_partida', '-')
        ciu_pa = self.data.get('delivery_cuidad_partida', '-')
        dis_pa = self.data.get('delivery_distrito_partida', '-')
        self.data['full_partida'] = f"{dir_pa}, {dep_pa} - {ciu_pa} - {dis_pa}".upper()

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "PUNTO DE PARTIDA", 0, 1, 'C')
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 4, self.data.get('full_partida', 'N/A'), 0, 'C')
        pdf.ln(2)

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "PUNTO DE LLEGADA", 0, 1, 'C')
        pdf.ln(1)

        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 4, self.data.get('full_llegada', 'N/A'), 0, 'C')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        anchuras = [8, 16, 10, 46]
        original_color = pdf.draw_color
        pdf.set_draw_color(255, 255, 255)

        pdf.set_font("Arial", '', 7)

        x2_start = pdf.get_x()
        pdf.cell(anchuras[0], 1, "COD.", 1, 0, 'C')
        pdf.cell(anchuras[1], 1, "CANT.", 1, 0, 'C')
        pdf.cell(anchuras[2], 1, "UNID.", 1, 0, 'C')
        pdf.cell(anchuras[3], 1, "DESCRIPCION", 1, 0, 'C')
        
        pdf.set_draw_color(original_color)

        pdf.set_xy(x2_start, pdf.get_y())

        pdf.ln(2)
        pdf.cell(0, 2, "", "T", 1)

        pdf.set_font("Arial", '', 8)
        
        pdf.set_draw_color(255, 255, 255)

        for items2 in self.data.get('items_DespatchLine', []):
            codigo = str(items2.get('id', 'N/A'))[:20]
            cantidad = str(items2.get('cantidad', '0'))[:6]
            unidad = str(items2.get('unidad', 'MTS'))[:4]
            descripcion = str(items2.get('descripcion', 'N/A'))
                 
            x_start = pdf.get_x()
            y_start = pdf.get_y()

            pdf.set_font("Arial", '', 8)

            pdf.cell(anchuras[0], 3, codigo, 1, 0, 'C')
            pdf.set_font("Arial", '', 10)

            pdf.set_char_spacing(1)
            pdf.cell(anchuras[1], 3, cantidad, 1, 0, 'C')
            pdf.set_char_spacing(0.0)

            pdf.set_font("Arial", '', 8)

            pdf.cell(anchuras[2], 3, unidad, 1, 0, 'C')


            pdf.multi_cell(anchuras[3], 3, descripcion, 0, 'C')
            
            pdf.ln(2)

        pdf.set_draw_color(original_color)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 4, "DATOS DEL TRANSPORTISTA", 0, 1, 'C')
        pdf.ln(1)
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 4, f"RUC: {self.data.get('ruc_transportista', 'N/A')}", 0, 1)

        pdf.multi_cell(0, 4, f"RAZÓN SOCIAL: {self.data.get('nombre_transportista', 'N/A').upper()}", 0, 'L')

        pdf.ln(2)
        pdf.cell(0, 1, "", "T", 1)
        pdf.ln(2)

        # QR

        url_qr = self.generar_url_qr_sunat()

        qr = qrcode.QRCode(box_size=10, border=1)
        qr.add_data(url_qr)
        qr.make(fit=True)
        
        img_qr = qr.make_image(fill_color="black", back_color="white")
        qr_temp_path = "temp_qr_dinamico.png"
        img_qr.save(qr_temp_path)
        pdf.image(qr_temp_path, x=25, w=30)
        
        if os.path.exists(qr_temp_path):
            os.remove(qr_temp_path)
        
        pdf.set_font("Arial", '', 8)
        pdf.multi_cell(0, 4, "Representación impresa de la Guía de Remisión Remitente Electrónica", 0, 'C')

        pdf.output(self.output_path)


def process_xml(
        xml_file, output_format, agency_name, other_notes,
        cliente_nombre_manual, 
        cliente_id_manual, 
        direccion_envio_manual,
        agencia_manual,
        otros_manual
        ) -> Tuple[str, str, str, str]:

    if xml_file is None:
        return (
            "<div class='preview-box'><p style='color: #94a3b8; text-align: center;'>Esperando archivo XML...</p></div>",
            None,
            "Por favor, sube un archivo XML para comenzar",
            None
        )

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp_xml:
            with open(xml_file.name, "rb") as f:
                tmp_xml.write(f.read())
            xml_path = tmp_xml.name

        if output_format == 'ticket':
            pdf_suffix = '_ticket.pdf'
        elif output_format == 'etiqueta_envio':
            pdf_suffix = '_etiqueta_envio.pdf' 
        elif output_format == 'etiqueta_envio_otro':
            pdf_suffix = '_etiqueta_envio_otro.pdf' 
        else:
            pdf_suffix = '_guia_de_remision.pdf' 
        with tempfile.NamedTemporaryFile(delete=False, suffix=pdf_suffix) as tmp_pdf:
            output_path = tmp_pdf.name
            
        extra_data = {
            'agency_name': agency_name,
            'other_notes': other_notes,
            'cliente_nombre_manual': cliente_nombre_manual,
            'cliente_id_manual': cliente_id_manual,
            'direccion_envio_manual': direccion_envio_manual,
            'agencia_manual': agencia_manual,
            'otros_manual': otros_manual
        }

        factura = FacturaXMLtoPDF(xml_path, output_path, extra_data)
        if factura.parse_xml():

            if output_format == 'etiqueta_envio':
                factura._generate_shipping_label_pdf()
            elif output_format == 'etiqueta_envio_otro':
                factura._generate_shipping_label_pdf_2()
            elif output_format == 'guia_de_remision':
                factura._generate_gre_ticket_pdf() 
            else:
                factura.generate_pdf(output_format)

            info = f"""CONVERSIÓN EXITOSA (Formato: {output_format.upper()})
                    Documento: {factura.data.get('tipo_documento', 'N/A')}
                    Número: {factura.data.get('numero_factura', 'N/A')}
                    Emisor: {factura.data.get('emisor_nombre', 'N/A')}
                    Cliente: {factura.data.get('cliente_nombre', 'N/A')}
                    Agencia: {agency_name or 'N/A'}
                    Otros: {other_notes or 'N/A'}
                    Total: {factura.format_currency(factura.data.get('total_pagar', '0.00'))}"""

            with open(output_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()
                pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

            pdf_html = f"""
            <div style='background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);'>
                <div style='text-align: center; margin-bottom: 15px;'>
                    <span style='color: #16a34a; font-weight: bold;'>PDF generado con éxito</span>
                </div>
                <div style='text-align: center; margin-top: 15px;'>
                    <a href='data:application/pdf;base64,{pdf_base64}' 
                    download='{factura.data.get('numero_factura', 'documento').replace(" ", "_").replace("/", "-")[:30]}_{factura.data.get('cliente_nombre', 'cliente').replace(" ", "_").replace("/", "-")}{pdf_suffix}'
                    style='                            
                    background: #4CAF50;
                            color: white;
                            padding: 10px 20px;
                            text-decoration: none;
                            border-radius: 6px;
                            display: inline-block;
                            font-size: 14px;
                            font-weight: 1000;
                       '>
                       Descargar PDF
                    </a>
                </div>
                
            </div>
            """
            
            return pdf_html, output_path, info, output_path
        else:
            error_html = "<div class='preview-box'><p style='color: #dc2626; text-align: center;'>❌ Error al procesar el archivo XML</p></div>"
            return error_html, None, "❌ El archivo XML no es válido o está corrupto", None

    except Exception as e:
        error_html = f"<div class='preview-box'><p style='color: #dc2626; text-align: center;'>❌ Error: {str(e)}</p></div>"
        return error_html, None, f"❌ Error inesperado: {str(e)}", None

def clear_inputs():
    xml_input_reset = gr.File(value=None)
    format_dropdown_reset = gr.Radio(value="ticket")

    agency_input_reset = gr.Text(value="")
    otros_input_reset = gr.Textbox(value="")

    nombre_manual_reset = gr.Text(value="")
    id_manual_reset = gr.Text(value="")
    direccion_manual_reset = gr.Textbox(value="")
    agencia_manual_reset = gr.Text(value="")
    otros_manual_reset = gr.Textbox(value="")

    agency_group_visibility_reset = gr.Group(visible=False)
    manual_group_visibility_reset = gr.Group(visible=False)
    
    pdf_viewer_reset = gr.HTML(
        value="<div class='preview-box'><p style='color: #94a3b8; text-align: center;'>El PDF aparecerá aquí después de la conversión</p></div>"
    )
    info_output_reset = gr.Textbox(value="")
    
    return (
        xml_input_reset, format_dropdown_reset, 
        agency_input_reset, otros_input_reset,
        nombre_manual_reset, id_manual_reset, direccion_manual_reset,
        agencia_manual_reset, otros_manual_reset,
        agency_group_visibility_reset, manual_group_visibility_reset,
        pdf_viewer_reset, info_output_reset
    )

def create_gradio_interface():
    def toggle_fields_optimized(choice):
        is_shipping_auto = choice == 'etiqueta_envio'
        is_shipping_manual = choice == 'etiqueta_envio_otro'
        
        agency_extra_visible = is_shipping_auto
        manual_fields_visible = is_shipping_manual

        return (
                gr.update(visible=agency_extra_visible),
                gr.update(visible=manual_fields_visible), 
        )

    with gr.Blocks(
        title="Conversor XML a PDF", 
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="gray"),
        css="""
        .gradio-container { max-width: 1200px !important; margin: 0 auto }
        .download-btn { background: #4CAF50 !important; color: white !important; }
        .preview-box { border: 2px dashed #e0e0e0; border-radius: 12px; padding: 30px; }
        .convert-shipping-btn { background: #FFA500 !important; color: white !important; }
        """
    ) as demo:
        gr.Markdown("""
        <div style='text-align: center; margin-bottom: 30px;'>
            <h1 style='color: #2563eb; margin-bottom: 10px;'>Conversor XML a PDF: Ticket y Etiqueta</h1>
        </div>
        """)
        
        with gr.Row():
            with gr.Column(scale=1.5):
                gr.Markdown("## 1. Subir Archivo y Seleccionar Formato")
                xml_input = gr.File(
                    label="Subir XML de Factura/Boleta", 
                    file_types=[".xml"],
                    elem_classes=["upload-box"]
                )
                
                output_format_dropdown = gr.Radio(
                    label="Formato de Salida",
                    choices=[("Ticket 80mm", "ticket"), ("Etiqueta 100x150mm", "etiqueta_envio"), ("Etiqueta 100x150mm (Recoge otra persona)", "etiqueta_envio_otro"), ("Guia de remision 80mm", "guia_de_remision")],
                    value="ticket",
                    interactive=True
                )
                
                with gr.Group(visible=False) as agency_extra_group:
                    gr.Markdown("## Información Adicional (Solo Etiqueta)")

                    agency_input = gr.Text(
                        label="Agencia:", 
                        value="", 
                        placeholder=""
                    ) 
                    
                    OTROS_input = gr.Textbox(
                        label="Otras Indicaciones:", 
                        value="", 
                        placeholder=""
                    ) 


                with gr.Group(visible=False) as manual_fields_group:
                    gr.Markdown("## Información Adicional (Solo Etiqueta de Recoge otra persona)")

                    cliente_nombre_manual_input = gr.Text(
                        label="Cliente:", 
                        value="", 
                        placeholder=""
                    )
                    cliente_id_manual_input = gr.Text(
                        label="RUC/DNI:", 
                        value="", 
                        placeholder=""
                    )
                    direccion_envio_manual_input = gr.Textbox(
                        label="Dirección:",
                        value="", 
                        placeholder=""
                    )
                    agencia_manual_input = gr.Text(
                        label="Agencia:", 
                        value="", 
                        placeholder=""
                    )
                    otros_manual_input = gr.Textbox(
                        label="Otras Indicaciones:",
                        value="", 
                        placeholder=""
                    )
                    
            with gr.Column(scale=2):
                gr.Markdown("## 2. Ejecutar botones")

                convert_btn = gr.Button(
                    "Convertir a PDF", 
                    variant="primary", 
                    size="lg",
                    elem_id="convert-btn"
                )

                clear_btn = gr.Button(
                    "Limpiar", 
                    variant="secondary", 
                    size="lg",
                    elem_id="clear-btn"
                )

                gr.Markdown("## 3. Descargar Archivo")
                pdf_viewer = gr.HTML(
                    label="",
                    value="<div class='preview-box'><p style='color: #94a3b8; text-align: center;'>El PDF aparecerá aquí después de la conversión</p></div>"
                )
                                
                gr.Markdown("Información del documento")
                info_output = gr.Textbox(
                    label="", 
                    interactive=False,
                    lines=8,
                    elem_classes=["info-box"]
                )

                current_pdf = gr.State()
                pdf_output = gr.File(label="PDF para descargar", visible=False)
        
        output_format_dropdown.change(
            fn=toggle_fields_optimized,
            inputs=[output_format_dropdown],
            outputs=[
            agency_extra_group, 
            manual_fields_group  
            ]
        )
        
        convert_btn.click(
            fn=process_xml,
            inputs=[
                xml_input, 
                output_format_dropdown, 
                agency_input,           
                OTROS_input,         
                cliente_nombre_manual_input, 
                cliente_id_manual_input,     
                direccion_envio_manual_input,
                agencia_manual_input,   
                otros_manual_input
            ],
            outputs=[pdf_viewer, current_pdf, info_output, pdf_output]
        )

        clear_btn.click(
            fn=clear_inputs,
            inputs=[],
            outputs=[
                xml_input, output_format_dropdown, agency_input, OTROS_input,
                cliente_nombre_manual_input, cliente_id_manual_input, direccion_envio_manual_input,
                agencia_manual_input, otros_manual_input,
                agency_extra_group, manual_fields_group,
                pdf_viewer, info_output
            ]
        )
        
        return demo

if __name__ == "__main__":
    os.makedirs("images", exist_ok=True)
    if not os.path.exists("images/logo_manchester.png"):
        print("Creando placeholder para logo_manchester.png")
    if not os.path.exists("images/qr_mostrario.png"):
        print("Creando placeholder para qr_mostrario.png")
        
    demo = create_gradio_interface()
    demo.launch(
        server_name="127.1.0.0",
        server_port=7860,
        share=False,
        #root_path="/MANCHESTERCOLLECTION/"
    )