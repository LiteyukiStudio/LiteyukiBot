# 写一个UINode基类，所有的UI节点都继承自这个基类
# 其他不同的基类例如文本，图像，面板都继承自UINode
# UI节点从任意树形节点可以被渲染通过Pillow
# UI节点可以被渲染成图片，也可以被渲染成PDF
# UI节点可以被渲染成图片，也可以被渲染成PDF
# UI节点可以被渲染成图片，也可以被渲染成PDF

# Path: src/api/canvas.py
class UINode:
    def __init__(self):
        self.children = []
        self.parent = None
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.visible = True
        self.z_index = 0
        self.background_color = None
        self.background_image = None
        self.border_color = None
        self.border_width = 0
        self.border_radius = 0
        self.border_style = None
        self.padding = 0
        self.margin = 0
        self.shadow = None

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def remove_child(self, child):
        self.children.remove(child)
        child.parent = None

    def render(self, canvas):
        if not self.visible:
            return
        self.render_background(canvas)
        self.render_border(canvas)
        self.render_padding(canvas)
        self.render_margin(canvas)
        self.render_shadow(canvas)
        self.render_self(canvas)
        self.render_children(canvas)

    def render_children(self, canvas):
        for child in self.children:
            child.render(canvas)


    def render_background(self, canvas):



    def render_border(self, canvas):
        pass

    def render_padding(self, canvas):
        pass

    def render_margin(self, canvas):
        pass

    def render_shadow(self, canvas):
        pass

    def render_self(self, canvas):
        pass
