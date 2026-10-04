"""Commercial cases from the reference PDFs; independent expected totals."""
from pathlib import Path
import pytest
from quotation_pdf import prepare_quotation, render_quotation

CASES = [
    ('barly', 'P02435', '2026-09-16', 'LABORATORIO BARLY S.A.',
     [(2, 'Servicios de Consultoria ERP- Base de Datos: Revision de problema con asiento de factura relacionado a compra.', 60)], .13, 120, 15.60, 135.60),
    ('coonaprosal', 'P02433', '2026-09-15', 'COOPERATIVA NACIONAL DE PRODUCTORES DE SAL R.L.',
     [(4, 'Cargar activos nuevos, sin ejecutar depreciaciones historicas.', 60),
      (4, 'Dar de baja activos, tomando en cuenta crear acciones sin modificacion contable.', 60),
      (4, 'Modificacion contable del retiro de activos fijos hecho de manera masiva.', 60)], .13, 720, 93.60, 813.60),
    ('expoflora', 'P02425', '2026-09-12', 'EXPOFLORA S.A.',
     [(7, 'Proyecto Expoflora Desarrollo: Simplificacion del cargador de lotes de semillas, la intencion es mejorar la ingesta de datos para el usuario.',55)], 0,385,0,385),
]


def example(case):
    name,number,date,client,lines,tax,*_ = case
    return dict(project_name=name,client_name=client,currency='USD',quote_number=number,quote_date=date,
                client={'address':'Dirección de prueba', 'email':name+'@example.test', 'phone':'00000000'},
                lines=[dict(quantity=q,description=d,unit_price=p) for q,d,p in lines],tax_rate=tax,
                requester='Solicitante de prueba' if name=='expoflora' else '',
                payment_method='Contado con Recibo' if name=='coonaprosal' else '8 Dias',
                observations='Solicitud de cambio # 37' if name=='expoflora' else '',
                project_reference='Solicitud de cambio para proyecto: Sistema Siembras Expoflora' if name=='expoflora' else '')


@pytest.mark.parametrize('case', CASES, ids=[c[0] for c in CASES])
def test_reference_totals_and_pdf(tmp_path,case):
    q=prepare_quotation(example(case))
    assert (q['subtotal'],q['tax_amount'],q['total']) == tuple(case[-3:])
    result=render_quotation(example(case),str(tmp_path/(case[0]+'.pdf')))
    assert Path(result['path']).read_bytes().startswith(b'%PDF')
    # Page count without introducing a runtime PDF-reader dependency.
    import re
    assert len(re.findall(rb'/Type\s*/Page\b',Path(result['path']).read_bytes())) == 2


def test_discount_rounding_and_currency():
    q=prepare_quotation(dict(lines=[dict(quantity=3,description='Servicio <ERP> & QA',unit_price='0.335')],
                             currency='CRC',discount_percent=.1,tax_rate=.13))
    assert (q['subtotal'],q['discount_amount'],q['tax_amount'],q['total']) == (1.02,.10,.12,1.04)


@pytest.mark.parametrize('field,value',[('tax_rate',-1),('tax_rate',1.1),('discount_percent',2),('currency','EUR'),('lines',[])])
def test_invalid_values(field,value):
    data=example(CASES[0]);data[field]=value
    with pytest.raises(ValueError):prepare_quotation(data)


@pytest.mark.parametrize('qty,price',[(0,60),(-2,60),(2,-60),(float('nan'),60),(2,float('inf'))])
def test_invalid_line(qty,price):
    with pytest.raises(ValueError):prepare_quotation(dict(lines=[dict(quantity=qty,unit_price=price,description='Servicio')]))


def test_overflow_does_not_write(tmp_path):
    data=example(CASES[0]);data['lines']*=80
    target=tmp_path/'overflow.pdf'
    with pytest.raises(ValueError,match='dos páginas'):render_quotation(data,str(target))
    assert not target.exists()


def test_banks_omitted_by_default(tmp_path):
    from quotation_pdf import STANDARD
    assert STANDARD['banks'] == []
    result = render_quotation(example(CASES[0]), str(tmp_path/'without-banks.pdf'))
    assert result['created'] is True
