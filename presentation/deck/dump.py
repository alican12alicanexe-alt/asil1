import sys, zipfile, re
from defusedxml import ElementTree as ET
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
z=zipfile.ZipFile(sys.argv[1] if len(sys.argv)>1 else 'ASELSAN-Sunum-Dolu.pptx')
# order from presentation.xml
pres=ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))
rels={r.get('Id'):r.get('Target') for r in pres}
p=ET.fromstring(z.read('ppt/presentation.xml'))
order=[rels[s.get('{%s}id'%NS['r'])] for s in p.find('p:sldIdLst',NS)]
for i,t in enumerate(order,1):
    name='ppt/'+t.replace('../','')
    root=ET.fromstring(z.read(name))
    print('='*70)
    print('POS %d  %s'%(i,name))
    for sp in root.iter('{%s}sp'%NS['p']):
        txs=sp.find('.//{%s}txBody'%NS['p'])
        if txs is None: continue
        lines=[]
        for para in txs.findall('{%s}p'%NS['a']):
            lvl=para.find('{%s}pPr'%NS['a'])
            l=lvl.get('lvl','0') if lvl is not None else '0'
            txt=''.join(t.text or '' for t in para.iter('{%s}t'%NS['a']))
            if txt.strip(): lines.append('   '+' '*(int(l)*2)+('- ' if l!='0' else '')+txt)
        if lines: print('\n'.join(lines))
    pics=[pic.find('.//{%s}cNvPr'%NS['p']) for pic in root.iter('{%s}pic'%NS['p'])]
    for pc in pics:
        if pc is not None: print('   [PIC] %s'%pc.get('name'))
    tbl=len(list(root.iter('{%s}tbl'%NS['a'])))
    if tbl: print('   [TABLE x%d]'%tbl)
    # notes
    nrel='ppt/slides/_rels/%s.rels'%name.split('/')[-1]
    try:
        nr=ET.fromstring(z.read(nrel))
        for r in nr:
            if 'notesSlide' in r.get('Type'):
                nroot=ET.fromstring(z.read('ppt/notesSlides/'+r.get('Target').split('/')[-1]))
                nt=' '.join(t.text or '' for t in nroot.iter('{%s}t'%NS['a']))
                nt=re.sub(r'^\s*\d+\s*','',nt)
                if nt.strip(): print('   NOT: '+nt.strip()[:600])
    except KeyError: pass
