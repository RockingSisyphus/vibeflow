class Runtime:
    def before_node(self, node_id, node_type, inputs):
        pass

    def after_node(self, node_id, node_type, outputs):
        pass

    def dispose(self):
        pass
