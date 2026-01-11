bl_info = {
    "name": "Vertex Group Hierarchy Sorter",
    "author": "Cloud Guy",
    "version": (1, 0, 2),
    "blender": (3, 0, 0),
    "location": "Properties > Object Data > Vertex Groups panel",
    "description": "List vertex groups in armature hierarchy order",
    "license": "GPL-3.0-or-later",
    "category": "Object",
}

import bpy
from typing import Dict

_VGH_SIGS: Dict[int, tuple] = {}

def find_armature_for_object(obj):
    if not obj:
        return None
    if obj.parent and obj.parent.type == "ARMATURE":
        return obj.parent
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            return mod.object
    return None

def filtered_bone_names(obj, armature):
    group_names = {vg.name for vg in obj.vertex_groups}
    return [bone.name for bone in armature.data.bones if bone.name in group_names]

def set_active_bone(armature, bone_name):
    if armature.mode != "POSE":
        return
    pbone = armature.pose.bones.get(bone_name)
    if not pbone:
        return
    for b in armature.data.bones:
        b.select = False
    pbone.bone.select = True
    armature.data.bones.active = pbone.bone

class VGH_UL_items(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        obj = context.object
        bones = getattr(data, propname)
        if not obj or obj.type != "MESH":
            return [], []
        groups = {vg.name for vg in obj.vertex_groups}
        flags = [
            self.bitflag_filter_item if bone.name in groups else 0
            for bone in bones
        ]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        depth = 0
        parent = item.parent
        while parent:
            depth += 1
            parent = parent.parent
        indent = "    " * depth
        branch = "" if depth == 0 else "|__ "
        layout.label(text=f"{indent}{branch}{item.name}", icon="BONE_DATA")

class VGH_OT_refresh_hierarchy_sorter(bpy.types.Operator):
    bl_idname = "object.vgh_refresh_hierarchy_sorter"
    bl_label = "Refresh"
    bl_description = "Refresh the hierarchy list after adding or deleting vertex groups"

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}
        armature = find_armature_for_object(obj)
        if not armature:
            return {"CANCELLED"}
        _apply_vgh_selection(obj, armature, getattr(obj.data, "vgh_index", -1))
        return {"FINISHED"}

def _visible_bone_indices(armature, group_names):
    bones = armature.data.bones
    return [i for i, bone in enumerate(bones) if bone.name in group_names]

def _vg_signature(obj):
    return tuple(vg.name for vg in obj.vertex_groups)

class DATA_PT_vertex_group_hierarchy_tools(bpy.types.Panel):
    bl_label = "Hierarchy Sorter"
    bl_idname = "DATA_PT_vertex_group_hierarchy_tools"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_parent_id = "DATA_PT_vertex_groups"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == "MESH"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        armature = find_armature_for_object(obj)
        if not armature:
            layout.label(text="No armature/vertex groups found.", icon="INFO")
            return
        filtered = filtered_bone_names(obj, armature)
        if not filtered:
            layout.label(text="No matching vertex groups.", icon="INFO")
            return
        _apply_vgh_selection(obj, armature, getattr(obj.data, "vgh_index", -1), set_active=False)

        row = layout.row(align=True)
        row.prop(obj.data, "vgh_auto_select_bone", text="Auto Select Bone", toggle=True)
        row.operator("object.vgh_refresh_hierarchy_sorter", text="", icon="FILE_REFRESH")
        if obj.data.vgh_auto_select_bone:
            in_weight_paint = obj.mode == "WEIGHT_PAINT"
            arm_selected = armature.select_get() if armature else False
            arm_in_pose = armature.mode == "POSE"
            if not (in_weight_paint and arm_selected and arm_in_pose):
                warn = layout.box()
                warn.label(
                    text="Select the armature, then Shift-click the mesh and go to Weight Paint mode.",
                    icon="ERROR",
                )

        box = layout.box()
        box.template_list(
            "VGH_UL_items",
            "",
            armature.data,
            "bones",
            obj.data,
            "vgh_index",
            rows=10,
        )

classes = (
    VGH_UL_items,
    VGH_OT_refresh_hierarchy_sorter,
    DATA_PT_vertex_group_hierarchy_tools,
)

def _vgh_index_update(self, context):
    obj = getattr(context, "object", None)
    if not obj or obj.type != "MESH":
        return
    armature = find_armature_for_object(obj)
    if not armature:
        return
    mesh = obj.data
    _apply_vgh_selection(obj, armature, getattr(mesh, "vgh_index", -1))

def _apply_vgh_selection(obj, armature, idx, *, set_active=True):
    if idx is None:
        return
    bones = armature.data.bones
    group_names = {vg.name for vg in obj.vertex_groups}
    visible_indices = _visible_bone_indices(armature, group_names)
    if not visible_indices:
        return

    if not (0 <= idx < len(bones)):
        idx = -1

    if idx in visible_indices:
        bone_idx = idx
    else:
        bone_idx = next((i for i in visible_indices if i > idx), None)
        if bone_idx is None:
            bone_idx = visible_indices[-1]

    mesh = obj.data
    if hasattr(mesh, "vgh_index") and mesh.vgh_index != bone_idx:
        mesh.vgh_index = bone_idx

    if not set_active:
        return

    bone = bones[bone_idx]
    vg = obj.vertex_groups.get(bone.name)
    if vg:
        obj.vertex_groups.active = vg
        if getattr(obj.data, "vgh_auto_select_bone", False):
            set_active_bone(armature, vg.name)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Mesh, "vgh_index"):
        bpy.types.Mesh.vgh_index = bpy.props.IntProperty(
            name="Hierarchy Sorter Index",
            default=0,
            update=_vgh_index_update,
            description="Internal index for the hierarchy sorter",
        )
    if not hasattr(bpy.types.Mesh, "vgh_auto_select_bone"):
        bpy.types.Mesh.vgh_auto_select_bone = bpy.props.BoolProperty(
            name="Auto Select Bone",
            description="When enabled, selecting a vertex group also selects the matching bone",
            default=False,
        )
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "_vgh_depsgraph_update":
            try:
                bpy.app.handlers.depsgraph_update_post.remove(h)
            except ValueError:
                pass
    bpy.app.handlers.depsgraph_update_post.append(_vgh_depsgraph_update)

def unregister():
    if _vgh_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_vgh_depsgraph_update)
    if hasattr(bpy.types.Mesh, "vgh_auto_select_bone"):
        del bpy.types.Mesh.vgh_auto_select_bone
    if hasattr(bpy.types.Mesh, "vgh_index"):
        del bpy.types.Mesh.vgh_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

def _vgh_depsgraph_update(scene, depsgraph):
    for update in depsgraph.updates:
        ob = getattr(update.id, "id_data", None)
        if not isinstance(ob, bpy.types.Object):
            continue
        if not hasattr(ob.data, "vgh_index"):
            continue
        if ob.type != "MESH":
            continue
        armature = find_armature_for_object(ob)
        if not armature:
            continue
        sig = _vg_signature(ob)
        key = ob.as_pointer()
        prev = _VGH_SIGS.get(key)
        if sig != prev:
            _VGH_SIGS[key] = sig
            _apply_vgh_selection(ob, armature, getattr(ob.data, "vgh_index", -1), set_active=False)

if __name__ == "__main__":
    register()