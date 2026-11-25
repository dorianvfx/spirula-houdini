"""Small procedural exterior used to demonstrate the generic Solaris bridge."""
import math
import numpy as np

COLORS={'siding':(.57,.58,.53),'trim':(.91,.89,.81),'roof':(.18,.19,.18),'wood':(.43,.25,.13),'grass':(.28,.43,.13),'asphalt':(.18,.19,.18),'glass':(.10,.17,.20),'stone':(.40,.39,.34),'leaves':(.16,.30,.09),'bark':(.28,.18,.09),'porch':(.58,.48,.34),'shutters':(.10,.11,.10)}


def geometry(node):
    import hou
    g=node.geometry();g.clear();g.addAttrib(hou.attribType.Prim,'name','');g.addAttrib(hou.attribType.Prim,'material','');g.addAttrib(hou.attribType.Point,'Cd',(1.,1.,1.))
    scale=np.array([node.evalParm('width')/11.4,node.evalParm('wall_height')/3.25,node.evalParm('depth')/7.6])
    def poly(vertices,part,material):
        vertices=np.asarray(vertices)*scale;points=g.createPoints(vertices.tolist());face=g.createPolygon()
        for p in points:p.setAttribValue('Cd',COLORS[material]);face.addVertex(p)
        face.setAttribValue('name',part);face.setAttribValue('material',material)
    def box(center,size,part,material):
        c=np.array(center);s=np.array(size)*.5;p=np.array([c+np.array([x,y,z])*s for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]])
        for f in [(0,3,2,1),(4,5,6,7),(0,4,7,3),(1,2,6,5),(3,7,6,2),(0,1,5,4)]:poly(p[list(f)],part,material)
    def beam(a,b,width,part,mat):
        a=np.array(a);b=np.array(b);d=b-a;d/=np.linalg.norm(d);side=np.cross(d,[0,0,1])
        if np.linalg.norm(side)<.01:side=np.cross(d,[0,1,0])
        side=side/np.linalg.norm(side)*width*.5;up=np.cross(d,side)
        vertices=[p+u*side+v*up for p in (a,b) for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:poly(np.array(vertices)[list(f)],part,mat)
    box((0,.13,0),(11.6,.26,7.8),'House/Foundation','stone')
    box((0,1.82,0),(11.4,3.1,7.6),'House/Walls','siding')
    for y in np.arange(.4,3.35,.18):
        box((0,y,-3.815),(11.4,.022,.04),'House/Cladding','trim' if False else 'siding')
        box((0,y,3.815),(11.4,.022,.04),'House/Cladding','siding')
        for x in (-5.715,5.715):box((x,y,0),(.04,.022,7.6),'House/Cladding','siding')
    for x in (-5.75,5.75):
        for z in (-3.84,3.84):box((x,1.82,z),(.16,3.15,.14),'House/CornerTrim','trim')
    # Main ridge runs along X; the porch ridge runs toward the front.
    for z in (-4.12,4.12):poly([(-6,3.42,z),(6,3.42,z),(6,5.0,0),(-6,5.0,0)],'House/Roof','roof')
    for x in (-5.7,5.7):poly([(x,3.34,-3.8),(x,3.34,3.8),(x,4.86,0)],'House/Gables','siding')
    for z in (-4.12,4.12):box((0,3.42,z),(12.1,.15,.16),'House/Fascia','trim')
    for x in (-6,6):
        for z in (-4.12,4.12):beam((x,3.42,z),(x,5,0),.15,'House/Fascia','trim')
    def window(x,z,w=1.25,h=1.65,y=1.9,side=False):
        if side:
            box((x,y,z),(.08,h,w),'House/Windows','glass')
            for zz in (z-w*.5,z+w*.5):box((x-.03,y,zz),(.13,h+.16,.09),'House/WindowTrim','trim')
            for yy in (y-h*.5,y+h*.5,y):box((x-.03,yy,z),(.13,.09,w+.16),'House/WindowTrim','trim')
            return
        box((x,y,z),(w,h,.09),'House/Windows','glass')
        for xx in (x-w*.5,x+w*.5,x):box((xx,y,z-.06),(.075,h+.14,.09),'House/WindowTrim','trim')
        for yy in (y-h*.5,y+h*.5,y-.1):box((x,yy,z-.06),(w+.14,.075,.09),'House/WindowTrim','trim')
        for xx in (x-w*.5-.24,x+w*.5+.24):
            box((xx,y,z+.01),(.30,h+.08,.10),'House/Shutters','shutters')
            for yy in np.arange(y-h*.5+.1,y+h*.5,.13):box((xx,yy,z-.06),(.28,.02,.03),'House/ShutterSlats','roof')
    window(-4.1,-3.96);window(-.95,-3.96,1.85,1.65);window(4.1,-3.96)
    for x in (-3.8,0,3.8):window(x,3.96,1.2,1.6)
    for z in (-1.8,1.5):window(-5.80,z,side=True);window(5.80,z,side=True)
    box((1.55,1.47,-3.98),(1.10,2.35,.15),'House/Door','wood')
    for x in (.96,2.14):box((x,1.48,-4.08),(.10,2.5,.10),'House/DoorTrim','trim')
    box((1.55,2.73,-4.08),(1.27,.1,.1),'House/DoorTrim','trim')
    for yy in (.85,1.9):
        for xx in (1.30,1.80):box((xx,yy,-4.07),(.35,.70,.025),'House/DoorPanels','porch')
    box((1.95,1.5,-4.12),(.04,.12,.04),'House/DoorHandle','roof')
    box((0,.35,-4.55),(5.8,.26,1.8),'House/PorchDeck','porch')
    for x in (-2.7,0,2.7):box((x,1.98,-5.28),(.15,3.0,.15),'House/PorchPosts','trim')
    for x in (-2.65,2.65):poly([(x,3.50,-5.55),(x,3.50,-2.65),(0,5.15,-2.65),(0,5.15,-5.55)],'House/PorchRoof','roof')
    poly([(-2.65,3.5,-5.53),(2.65,3.5,-5.53),(0,5.15,-5.53)],'House/PorchGable','siding')
    for y in np.arange(3.6,5.05,.16):
        half=2.65*(5.15-y)/1.65
        box((0,y,-5.56),(2*half,.025,.04),'House/PorchCladding','siding')
    for x in (-2.65,2.65):beam((x,3.5,-5.64),(0,5.15,-5.64),.16,'House/PorchFascia','trim')
    box((0,3.49,-5.56),(5.7,.17,.18),'House/PorchBeam','trim')
    for a,b in [((-1.05,4.48,-5.69),(1.05,4.48,-5.69)),((0,4.48,-5.69),(0,4.95,-5.69)),((0,4.48,-5.69),(-.56,4.79,-5.69)),((0,4.48,-5.69),(.56,4.79,-5.69))]:beam(a,b,.09,'House/GableWood','wood')
    for lo,hi in [(-2.7,.55),(2.5,2.7)]:
        for yy in (.64,1.42):box(((lo+hi)/2,yy,-5.28),(hi-lo,.09,.09),'House/Railing','trim')
        for xx in np.arange(lo+.1,hi,.20):box((xx,1.02,-5.28),(.045,.77,.045),'House/Railing','trim')
    for i in range(3):box((1.55,.08+i*.10,-6.08+i*.24),(1.9,.16+i*.20,.50),'House/Steps','porch')
    box((0,-.07,0),(32,.12,30),'Landscape/Lawn','grass')
    box((7.4,.005,-6.7),(6.5,.06,13),'Landscape/Driveway','asphalt')
    box((2.8,.012,-7.1),(4.2,.05,2.3),'Landscape/Path','asphalt')
    rng=np.random.default_rng(42)
    def ellipsoid(center,radii,part,mat):
        rings=6;slices=10
        for i in range(rings):
            for j in range(slices):
                pts=[]
                for ii,jj in [(i,j),(i,j+1),(i+1,j+1),(i+1,j)]:
                    a=math.pi*(ii+.01)/(rings+.02);b=2*math.pi*jj/slices
                    pts.append(np.array(center)+np.array(radii)*[math.sin(a)*math.cos(b),math.cos(a),math.sin(a)*math.sin(b)])
                poly(pts,part,mat)
    for x in np.arange(-5.1,5.2,1.1):
        if -.8<x<2.8:continue
        ellipsoid((x,.43,-4.35),(.65,.38,.48),'Landscape/Shrubs','leaves')
    for x,z in [(-10,1),(-9,7),(-5,10),(0,11),(6,10),(10,5)]:
        box((x,1.65,z),(.30,3.3,.30),'Landscape/TreeTrunks','bark')
        for i in range(3):ellipsoid((x+rng.uniform(-.8,.8),3.5+i*.7,z+rng.uniform(-.8,.8)),(1.7,1.7,1.6),'Landscape/Trees','leaves')


def usd_geometry(node):
    import hou
    from pxr import UsdGeom,Gf,Vt
    stage=node.editableStage();UsdGeom.Xform.Define(stage,'/World');UsdGeom.Xform.Define(stage,'/World/House');UsdGeom.Xform.Define(stage,'/World/Landscape')
    source=hou.node(node.evalParm('sop_source'));geo=source.geometry();groups={}
    for prim in geo.prims():groups.setdefault((prim.stringAttribValue('name'),prim.stringAttribValue('material')),[]).append(prim)
    for (name,mat),prims in groups.items():
        mesh=UsdGeom.Mesh.Define(stage,'/World/'+name);positions=[];counts=[]
        for prim in prims:
            vertices=[v.point().position()*source.creator().worldTransform() for v in prim.vertices()];counts.append(len(vertices));positions.extend(vertices)
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in positions]));mesh.CreateFaceVertexCountsAttr(counts);mesh.CreateFaceVertexIndicesAttr(list(range(len(positions))));mesh.CreateSubdivisionSchemeAttr('none');mesh.CreateDoubleSidedAttr(True)
        mesh.GetPrim().SetCustomDataByKey('spirula_material',mat)


def materials(node):
    from pxr import UsdShade,Sdf,Gf
    stage=node.editableStage()
    for name,color in COLORS.items():
        value=node.evalParmTuple(name) if node.parm(name+'r') else color
        srgb=np.asarray(value);linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
        mat=UsdShade.Material.Define(stage,'/Looks/'+name);shader=UsdShade.Shader.Define(stage,'/Looks/'+name+'/Surface');shader.CreateIdAttr('UsdPreviewSurface');shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*linear));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.16 if name=='glass' else .8);shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(.25 if name=='glass' else 0.);mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    for prim in stage.Traverse():
        material=prim.GetCustomDataByKey('spirula_material')
        if material:UsdShade.MaterialBindingAPI.Apply(prim).Bind(UsdShade.Material(stage.GetPrimAtPath('/Looks/'+material)))


def lighting(node):
    from pxr import UsdLux,UsdGeom,Gf
    stage=node.editableStage();sun=UsdLux.DistantLight.Define(stage,'/Lights/Sun');sun.CreateIntensityAttr(node.evalParm('sun'));sun.CreateAngleAttr(.8);sun.CreateColorAttr(Gf.Vec3f(1.,.90,.76));UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(-35,145,0))
    dome=UsdLux.DomeLight.Define(stage,'/Lights/Sky');dome.CreateIntensityAttr(node.evalParm('sky'));dome.CreateColorAttr(Gf.Vec3f(.68,.81,1.))


def create():
    import hou
    geo=hou.node('/obj').createNode('geo','MAISON_DEMO');model=geo.createNode('python','MAISON_PROCEDURALE');group=model.parmTemplateGroup()
    for name,label,value in [('width','Largeur maison',11.4),('depth','Profondeur maison',7.6),('wall_height','Hauteur des murs',3.25)]:group.append(hou.FloatParmTemplate(name,label,1,default_value=(value,),min=.1))
    model.setParmTemplateGroup(group);model.parm('python').set('import hou,spirula_house_demo\nspirula_house_demo.geometry(hou.pwd())');out=geo.createNode('null','OUT_MAISON');out.setInput(0,model);out.setDisplayFlag(True);out.setRenderFlag(True);geo.layoutChildren();geo.setDisplayFlag(False)
    stage=hou.node('/stage');source=stage.createNode('pythonscript','MAISON_GEOMETRIE');group=source.parmTemplateGroup();group.append(hou.StringParmTemplate('sop_source','Géométrie SOP',1,default_value=(out.path(),)));source.setParmTemplateGroup(group);source.parm('python').set('import hou,spirula_house_demo\nspirula_house_demo.usd_geometry(hou.pwd())')
    mats=stage.createNode('pythonscript','MAISON_MATERIAUX');mats.setInput(0,source);group=mats.parmTemplateGroup()
    for name in ('siding','trim','roof','wood','grass'):
        parm=hou.FloatParmTemplate(name,name.capitalize(),3,default_value=COLORS[name]);parm.setNamingScheme(hou.parmNamingScheme.RGBA);parm.setLook(hou.parmLook.ColorSquare);group.append(parm)
    mats.setParmTemplateGroup(group);mats.parm('python').set('import hou,spirula_house_demo\nspirula_house_demo.materials(hou.pwd())')
    lights=stage.createNode('pythonscript','SOLEIL_ET_CIEL');lights.setInput(0,mats);group=lights.parmTemplateGroup()
    for name,label,value in [('sun','Intensité soleil',10.),('sky','Intensité ciel',1.2)]:group.append(hou.FloatParmTemplate(name,label,1,default_value=(value,),min=0))
    lights.setParmTemplateGroup(group);lights.parm('python').set('import hou,spirula_house_demo\nspirula_house_demo.lighting(hou.pwd())')
    units=stage.createNode('configurelayer','UNITES_METRES');units.setInput(0,lights);units.parm('setstagemetadata').set(1);units.parm('setupaxis').set(1);units.parm('upaxis').set('y');units.parm('setmetersperunit').set(1);units.parm('metersperunit').set(1.)
    final=stage.createNode('null','OUT_SCENE_MAISON');final.setInput(0,units);final.setDisplayFlag(True);stage.layoutChildren();return final
