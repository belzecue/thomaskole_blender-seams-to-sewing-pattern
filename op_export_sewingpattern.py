import bpy
from os.path import basename
from xml.sax.saxutils import escape
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    IntVectorProperty,
    FloatProperty,
)
import bmesh
import mathutils
import random

class Export_Sewingpattern(bpy.types.Operator):
    """Export Sewingpattern"""

    bl_idname = "object.export_sewingpattern"
    bl_label = "Export Sewing Pattern"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(
        subtype='FILE_PATH',
    )
    alignment_markers: EnumProperty(
        items=(
            ('OFF', "Off",
             "No alignment markers"),
            ('SEAM', "Marked as seam",
             "Use sewing edges manually marked as seam"),
            ('AUTO', "Autodetect + seam",
             "Finds sewing edges of corners automatically and marks them as seam"),
        ),
        name="Alignment markers",
        description="Exports matching colored lines on the borders of sewing patterns to assist with alignment",
        default='AUTO',
    )
    file_format: EnumProperty(
        items=(
            ('SVG', "Scalable Vector Graphic (.svg)",
             "Export the sewing pattern to a .SVG file"),
            ('PNG', "PNG Image (.png)",
             "Export the sewing pattern to a .PNG file")
        ),
        name="Format",
        description="File format to export the UV layout to",
        default='SVG',
    )
    size: IntVectorProperty(
        size=2,
        default=(1024, 1024),
        min=8, max=32768,
        description="Dimensions of the exported file",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.data.uv_layers

    def invoke(self, context, event):
        #stuff to check / set before goes here :)
        self.filepath = self.get_default_file_name(context) + "." + self.file_format.lower()
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def get_default_file_name(self, context):
        return context.active_object.name

    def check(self, context):
        if any(self.filepath.endswith(ext) for ext in (".png", ".eps", ".svg")):
            self.filepath = self.filepath[:-4]

        ext = "." + self.file_format.lower()
        self.filepath = bpy.path.ensure_ext(self.filepath, ext)
        return True

    def execute(self, context):
        obj = context.active_object
        is_editmode = (obj.mode == 'EDIT')
        if is_editmode:
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

        filepath = self.filepath
        filepath = bpy.path.ensure_ext(filepath, "." + self.file_format.lower())
        
        if (self.alignment_markers == 'AUTO'):
            self.auto_detect_markers()

        self.export(filepath)

        if is_editmode:
            bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        return {'FINISHED'}
    
    def export(self, filepath):
        svgstring = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + str(self.size[0]) + ' ' + str(self.size[1]) +'">'
        #svgstring += '<!-- Exported using the Seams to Sewing pattern for Blender  -->'
        svgstring += '\n<defs><style>.seam{stroke: #000; stroke-width:1px; fill:white} .sewinguide{stroke-width:1px;}</style></defs>'
        
        #get loops:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type="EDGE")
        bpy.ops.mesh.select_all(action='SELECT')

        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        bpy.ops.mesh.region_to_loop()

        boundary_loop = [e for e in bm.edges if e.select]

        relevant_loops=[]

        for e in boundary_loop:
            relevant_loops.append(e.link_loops[0])
    
        loop_groups = [[]]
        
        while (len(relevant_loops) > 0):
            temp_group = [relevant_loops[0]]
            vertex_to_match = relevant_loops[0].link_loop_next.vert
            relevant_loops.remove(relevant_loops[0])
            match = True
            while(match == True):
                match = False
                for x in range(0, len(relevant_loops)):
                    if (relevant_loops[x].link_loop_next.vert == vertex_to_match):
                        temp_group.append(relevant_loops[x])
                        vertex_to_match = relevant_loops[x].vert
                        relevant_loops.remove(relevant_loops[x])
                        match = True
                        break
                    if (relevant_loops[x].vert == vertex_to_match):
                        temp_group.append(relevant_loops[x])
                        vertex_to_match = relevant_loops[x].link_loop_next.vert
                        relevant_loops.remove(relevant_loops[x])
                        match = True
                        break
            loop_groups.append(temp_group)
            
        uv_layer = bm.loops.layers.uv.active   

        for lg in loop_groups:
            if (len(lg) == 0):
                continue
            lg.append(lg[0])
            svgstring += '\n<g>'
            #border
            svgstring += '<path class="seam" d="M ' 
            for l in lg:
                uv = l[uv_layer].uv.copy()
                svgstring += str(uv.x*self.size[0])
                svgstring += ','
                svgstring += str((1-uv.y)*self.size[1])
                svgstring += ' '
            svgstring += '"/></g>'
            #markers
            if (self.alignment_markers != 'OFF'):
                for l in lg:
                    has_wire = False
                    for w in l.vert.link_edges:
                        if w.is_wire and w.seam:
                            has_wire = True
                            svgstring += self.add_alignment_marker(l, w, uv_layer)
            
        
        svgstring += '\n</svg>'
        
        with open(filepath, "w") as file:
            file.write(svgstring)
            
        bpy.ops.object.mode_set(mode='OBJECT')
        
    def add_alignment_marker(self, loop, wire, uv_layer):
        wire_dir = mathutils.Vector((0,0));
        for l in loop.vert.link_edges:
            if (len(l.link_loops) > 0 and len(l.link_faces) == 1):
                this_dir = l.link_loops[0][uv_layer].uv - l.link_loops[0].link_loop_next[uv_layer].uv
                if (l.link_loops[0].vert == loop.vert):
                    wire_dir -= this_dir
                else:
                    wire_dir -= this_dir
        
        wire_dir.normalize()
        wire_dir.y *= -1;
        wire_dir.xy = wire_dir.yx
        wire_dir *= 0.01;
        
        sew_color = mathutils.Color((1,0,0))
        color_hash = (hash(wire))
        color_hash /= 100000000.0
        color_hash *= 1345235.23523
        color_hash %= 1.0
        sew_color.hsv = color_hash, 1, 1
        sew_color_hex = "#%.2x%.2x%.2x" % (int(sew_color.r * 255), int(sew_color.g * 255), int(sew_color.b * 255))
        
        returnstring = '<path class="sewinguide" stroke="' + sew_color_hex + '" d="M '
        uv1 = loop[uv_layer].uv.copy();
        uv1.y = 1-uv1.y;
        returnstring += str((uv1.x + wire_dir.x) * self.size[0])
        returnstring += ','
        returnstring += str((uv1.y + wire_dir.y) * self.size[1])
        returnstring += ' '
    
        returnstring += str((uv1.x - wire_dir.x) * self.size[0])
        returnstring += ','
        returnstring += str((uv1.y - wire_dir.y) * self.size[1])
        returnstring += ' '
        returnstring += '"/>\n'  
        
        return returnstring
        
    def auto_detect_markers(self):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type="EDGE")
        bpy.ops.mesh.select_all(action='SELECT')

        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        bpy.ops.mesh.region_to_loop()

        bpy.ops.mesh.select_mode(type="VERT")

        boundary_vertices = [v for v in bm.verts if v.select]

        for v in boundary_vertices:
            intrest = 0
            for e in v.link_edges:
                if (len(e.link_faces) != 0):
                    intrest += 1;
            if intrest == 2:
                for l in v.link_edges:
                    if (len(l.link_faces) == 0):
                        l.seam = True
        
    