class ProcessBase:
    def run_pure(self, inputs, params):
        return {"processed_payload": inputs["payload.internal"]["value"]}
