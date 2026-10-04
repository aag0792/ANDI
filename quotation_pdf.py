"""AND quotation layout; no database or external side effects."""
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfgen import canvas

ASSETS = Path(__file__).resolve().parent / 'assets'
STANDARD = json.loads((ASSETS / 'quote-standard.json').read_text(encoding='utf-8'))
ORANGE = colors.HexColor('#ef7d00')
GRAY = colors.HexColor('#808080')
CENT = Decimal('0.01')


def number(value, name, maximum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{name}: número inválido') from None
    if not result.is_finite() or result < 0 or (maximum is not None and result > maximum):
        raise ValueError(f'{name}: fuera de rango')
    return result


def prepare_quotation(data):
    """Normalize legacy estimates or explicit commercial lines. Rates are fractions."""
    q = dict(data)
    currency = q.get('currency', 'CRC')
    if currency not in ('USD', 'CRC'):
        raise ValueError('currency debe ser USD o CRC')
    raw = q.get('lines')
    if raw is None:
        raw = [{'quantity': 1, 'description': q.get('description') or q.get('project_name', 'Proyecto'),
                'unit_price': q.get('total_cost', 0)}]
    if not raw:
        raise ValueError('Se requiere al menos una línea')
    lines = []
    for item in raw:
        qty = number(item['quantity'], 'quantity')
        price = number(item['unit_price'], 'unit_price').quantize(CENT, rounding=ROUND_HALF_UP)
        if qty == 0 or not str(item.get('description', '')).strip():
            raise ValueError('Cada línea requiere cantidad positiva y descripción')
        lines.append({'quantity': float(qty), 'description': str(item['description']),
                      'unit_price': float(price), 'total': float((qty * price).quantize(CENT, rounding=ROUND_HALF_UP))})
    subtotal = sum((Decimal(str(x['total'])) for x in lines), Decimal(0))
    discount_rate = number(q.get('discount_percent', 0), 'discount_percent', Decimal(1))
    tax_rate = number(q.get('tax_rate', 0), 'tax_rate', Decimal(1))
    discount = (subtotal * discount_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    tax = ((subtotal - discount) * tax_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    quote_date = q.get('quote_date') or datetime.now(ZoneInfo('America/Costa_Rica')).date().isoformat()
    datetime.strptime(quote_date, '%Y-%m-%d')
    q.update(currency=currency, lines=lines, subtotal=float(subtotal), discount_amount=float(discount),
             tax_amount=float(tax), total=float(subtotal - discount + tax),
             discount_percent=float(discount_rate), tax_rate=float(tax_rate), quote_date=quote_date)
    return q


def render_quotation(data, output_path):
    q = prepare_quotation(data)
    width = 540
    style = ParagraphStyle('quote', fontName='Helvetica', fontSize=10, leading=14)
    def p(value, bold=False, size=10, white=False, align=0):
        s = ParagraphStyle('cell', parent=style, fontName='Helvetica-Bold' if bold else 'Helvetica',
                           fontSize=size, leading=size+3, alignment=align, textColor=colors.white if white else colors.black)
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), s)
    def table(rows, widths, commands=()):
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),
                              ('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),2),
                              ('BOTTOMPADDING',(0,0),(-1,-1),2)] + list(commands)))
        return t
    def band(text, color=GRAY):
        return table([[p(text, True, 11, True, align=1)]],[width],[('BACKGROUND',(0,0),(-1,-1),color),('ALIGN',(0,0),(-1,-1),'CENTER')])
    company = {**STANDARD['company'], **q.get('company', {})}
    client = q.get('client', {})
    def field(*keys):
        return next((client[k] for k in keys if client.get(k) is not None), '')
    number_label = q.get('quote_number') or 'BORRADOR'
    issuer = '\n'.join([company['name'], 'NIT: '+company['tax_id'], company['address'],
                        'Teléfono: '+company['phone'], 'Email: '+company['email']])
    from reportlab.platypus import Image
    logo = Image(str(ASSETS/'quote-logo.png'), width=104, height=60, kind='proportional')
    header = table([[logo,p(issuer, size=9),p('COTIZACION\nN°: '+number_label+'\n\nFecha: '+datetime.strptime(q['quote_date'],'%Y-%m-%d').strftime('%d/%m/%Y'),True, align=1)]],
                   [110,252,178],[('BOX',(2,0),(2,0),1,colors.black)])
    details = table([[p(label,True,10,True),p(value)] for label,value in [
        ('Cliente:',field('name','NOMBRE','nombre') or q.get('client_name','')),
        ('Dirección:',field('address','DIRECCION','direccion')),('Tel:',field('phone','TELEFONO1','telefono')),
        ('Email:',field('email','E_MAIL','EMAIL'))]], [74,466], [('BACKGROUND',(0,0),(0,-1),GRAY)])
    meta = table([[p(s,True,10,True,align=1) for s in ('Solicitante','Forma de Pago','Moneda')],
                  [p(q.get('requester',''),align=1),p(q.get('payment_method') or field('payment_method','CONDICION_PAGO'),align=1),p('Dólar' if q['currency']=='USD' else 'Colón',align=1)]],
                 [260,170,110],[('BACKGROUND',(0,0),(-1,0),ORANGE)])
    symbol = '$' if q['currency']=='USD' else 'CRC'
    def money(v): return f'{symbol} {v:,.2f}'
    rows = [[p(s,True,10,True,align=1) for s in ('Cant.','Descripción','Precio','Total')]]
    rows += [[p(f"{x['quantity']:.1f}",align=1),p(x['description'],size=11),p(money(x['unit_price']),align=2),p(money(x['total']),align=2)] for x in q['lines']]
    items = table(rows,[52,298,84,106],[('BACKGROUND',(0,0),(-1,0),ORANGE),
          ('LINEBEFORE',(0,1),(-1,-1),.6,colors.black),('LINEAFTER',(-1,1),(-1,-1),.6,colors.black),
          ('LINEBELOW',(0,-1),(-1,-1),2,colors.black),('BOTTOMPADDING',(0,1),(-1,-1),14)])
    totals = table([[p(label,True,align=2),p(money(value),True,align=2)] for label,value in [
        ('Sub total:',q['subtotal']),(f"Desc. {q['discount_percent']*100:g}%:",q['discount_amount']),
        ('IVA:',q['tax_amount']),('TOTAL:',q['total'])]],[84,102],[('GRID',(0,0),(-1,-1),1,colors.black)])
    summary = table([[p(q.get('project_reference','')),totals]],[350,190])
    banks = q.get('banks',STANDARD['banks'])
    blocks = [(header,6),(details,2),(meta,4),(items,6),(summary,2),
              (band('OBSERVACIONES'),2),(p(q.get('observations','')),24)]
    if banks:
        blocks += [(band('CUENTAS BANCARIAS'),0),(p('\n'.join(banks),size=8,align=1),0)]
    terms = [band('CONDICIONES GENERALES'+' '*6+'Cotización N°: '+number_label,ORANGE)]
    term_rows=[]
    for section in q.get('terms',STANDARD['terms']):
        term_rows.append([p(section['title'],True,9)])
        term_rows.append([p(section['text'],size=9)])
    terms += [table(term_rows,[width],[('BOX',(0,0),(-1,-1),.7,colors.black)]),p('Aprobación Cliente: _________________________',True)]
    # Preflight both pages: reject oversize content instead of truncating or overlapping.
    measured=[(b,b.wrap(width,700)[1],gap) for b,gap in blocks]
    term_sizes=[t.wrap(width,700)[1] for t in terms]
    if sum(h+g for _,h,g in measured)>690 or sum(term_sizes)+85>725:
        raise ValueError('El contenido excede el formato de dos páginas; reduzca el detalle o las condiciones')
    target=Path(output_path)
    target.parent.mkdir(parents=True,exist_ok=True)
    pdf=canvas.Canvas(str(target),pagesize=letter)
    pdf.setTitle('Cotización '+number_label+' - '+str(q.get('client_name','')))
    def footer(page):
        pdf.setStrokeColor(colors.black);pdf.line(46,26,480,26)
        pdf.setFont('Helvetica',7);pdf.drawRightString(576,24,f'Página {page} de 2')
    y=762
    for block,h,gap in measured:
        block.drawOn(pdf,36,y-h);y-=h+gap
    footer(1);pdf.showPage()
    y=772
    for i,(block,h) in enumerate(zip(terms,term_sizes)):
        block.drawOn(pdf,36,y-h);y-=h+(8 if i==0 else 60)
    footer(2);pdf.save()
    return {'created':True,'path':str(target),'filename':target.name,'quotation':q}
