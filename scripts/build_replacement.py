import hou
from pathlib import Path
root=Path(__file__).resolve().parents[1];file=str(root/'otls/SpirulaReplacement.hda');geo=hou.node('/obj').createNode('geo','BUILD_REPLACE')
def button(name,label,code):
 p=hou.ButtonParmTemplate(name,label)
 if name in ('select','protect_select'):p.setScriptCallback('import spirula_replace;n=kwargs["node"];'+code)
 else:p.setScriptCallback('import hou,spirula_replace;hou.ui.postEventCallback(lambda n=kwargs["node"]: '+code+')')
 p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p
for role,label,inputs,parms in [
 ('selection','02A · Sélection de l’objet à retirer',1,[hou.MenuParmTemplate('mode','Sélection',['points','box'],['Points du viewport','Volume orienté']),hou.StringParmTemplate('points','Points à retirer',1),hou.StringParmTemplate('protect','Points du décor à protéger',1),button('protect_select','Protéger du décor dans le viewport',"spirula_replace.dispatch(n,'protect')"),hou.StringParmTemplate('status','Résultat',1,default_value=('Aucune sélection appliquée',)),button('preview','Voir uniquement les points sélectionnés',"spirula_replace.dispatch(n,'preview')"),button('apply','Afficher le scan après suppression',"spirula_replace.dispatch(n,'apply')"),button('clear','Effacer la sélection',"spirula_replace.dispatch(n,'clear')"),button('select','1 · Sélectionner dans le viewport',"spirula_replace.dispatch(n,'select')"),button('commit','2 · Appliquer la sélection du viewport',"spirula_replace.dispatch(n,'commit')"),hou.FloatParmTemplate('center','Centre du volume',3),hou.FloatParmTemplate('size','Taille du volume',3,default_value=(1,2,1)),hou.FloatParmTemplate('rotation','Rotation du volume',3),hou.FloatParmTemplate('margin','Marge sur les centres',1,default_value=(0,))]),
 ('remove','02B · Retrait réversible',1,[hou.ToggleParmTemplate('enabled','Retirer les points sélectionnés',default_value=True)]),
 ('repair','02E · Décor réparé / solution manuelle',2,[hou.ToggleParmTemplate('enabled','Inclure la réparation',default_value=False),button('build','Solution manuelle : convertir SURFACE_FOND_A_MODELER',"spirula_replace.dispatch(n,'build')")])]:
 n=geo.createNode('subnet',role);templates=hou.ParmTemplateGroup(parms)
 py=n.createNode('python','EVALUER');py.parm('python').set('import hou,spirula_replace\nspirula_replace.evaluate(hou.pwd(),'+repr(role)+')')
 for i in range(inputs):py.setInput(i,n.indirectInputs()[i])
 out=n.createNode('output');out.setInput(0,py);out.setDisplayFlag(True);out.setRenderFlag(True)
 a=n.createDigitalAsset(name='spirula::replace_'+role+'::1.0',hda_file_name=file,description=label,min_num_inputs=1,max_num_inputs=inputs,create_backup=False);a.type().definition().setParmTemplateGroup(templates)
geo.destroy();print('REPLACEMENT_BUILT')
