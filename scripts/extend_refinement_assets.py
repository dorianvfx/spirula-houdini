import hou

def extend_all():
    source=hou.nodeType(hou.sopNodeTypeCategory(),'spirula::arch_source::1.0')
    if source and 'OnLoaded' in source.definition().sections():
        d=source.definition();d.addSection('OnLoaded',d.sections()['OnLoaded'].contents().replace("!='7.2.0'","!='7.3.0'"));d.setExtraFileOption('OnLoaded/IsPython',True)
    t=hou.nodeType(hou.sopNodeTypeCategory(),'spirula::arch_result::1.0')
    if t:
        d=t.definition();g=d.parmTemplateGroup()
        if not g.find('add_refinement'):
            p=hou.ButtonParmTemplate('add_refinement','Ajouter / ouvrir le parcours de raffinement local');p.setScriptCallback("import spirula_refine;spirula_refine.create(kwargs['node'])");p.setScriptCallbackLanguage(hou.scriptLanguage.Python);g.insertBefore('next',p);d.setParmTemplateGroup(g)
    print('REFINEMENT_INTEGRATION_READY',flush=True)

if __name__=='__main__':extend_all()
