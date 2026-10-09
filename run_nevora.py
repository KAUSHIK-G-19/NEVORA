import onnxruntime as ort
import numpy as np

session = ort.InferenceSession("nevora_pinn.onnx")

input_name = session.get_inputs()[0].name
input_data = np.array([[400.0, -25.0, 35.0, 80.0]], dtype=np.float32)

outputs = session.run(None, {input_name: input_data})

print("Outputs:", outputs)