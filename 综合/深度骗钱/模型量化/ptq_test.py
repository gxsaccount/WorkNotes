import numpy as np

# ======================
# 1. 模型定义（支持中间激活捕获）
# ======================
class CNNWithSoftmax:
    def __init__(self, in_channels=3, out_channels=16, input_size=28):
        # 初始化随机权重
        self.conv_weights = np.random.randn(out_channels, in_channels, 3, 3) * 0.1
        self.conv_bias = np.zeros(out_channels)
        self.fc_weights = np.random.randn(16 * (input_size-2)**2, 10) * 0.01
        self.fc_bias = np.zeros(10)
        
        # 用于存储中间激活
        self.conv_activation = None
        self.fc_input = None
    
    def conv_forward(self, x):
        # 简化的卷积实现（无填充，步长1）
        batch_size, in_channels, height, width = x.shape
        out_channels, _, kernel_h, kernel_w = self.conv_weights.shape
        out_height = height - kernel_h + 1
        out_width = width - kernel_w + 1
        
        # 初始化输出
        output = np.zeros((batch_size, out_channels, out_height, out_width))
        
        # 执行卷积
        for b in range(batch_size):
            for oc in range(out_channels):
                for ic in range(in_channels):
                    for i in range(out_height):
                        for j in range(out_width):
                            output[b, oc, i, j] += np.sum(
                                x[b, ic, i:i+kernel_h, j:j+kernel_w] * 
                                self.conv_weights[oc, ic]
                            )
                output[b, oc] += self.conv_bias[oc]
        
        self.conv_activation = output  # 存储激活值
        return output
    
    def relu(self, x):
        return np.maximum(x, 0)
    
    def flatten(self, x):
        batch_size = x.shape[0]
        return x.reshape(batch_size, -1), (batch_size, x.shape[1], x.shape[2], x.shape[3])
    
    def fc_forward(self, x):
        self.fc_input = x  # 存储全连接层输入
        return x @ self.fc_weights + self.fc_bias
    
    def softmax(self, x):
        exp_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=1, keepdims=True)
    
    def forward(self, x):
        # 前向传播流程
        conv_out = self.conv_forward(x)
        relu_out = self.relu(conv_out)
        flattened, _ = self.flatten(relu_out)
        fc_out = self.fc_forward(flattened)
        probs = self.softmax(fc_out)
        return probs

# ======================
# 2. PTQ校准器（捕获中间激活）
# ======================
class PTQCalibrator:
    def __init__(self, model):
        self.model = model
        self.activation_stats = {}  # 存储各层统计信息
    
    def collect_statistics(self, calibration_data):
        """收集校准数据"""
        print("Running calibration...")
        # 运行前向传播（模型会自动存储激活值）
        _ = self.model.forward(calibration_data)
        
        # 收集卷积层激活统计
        if self.model.conv_activation is not None:
            min_val = np.min(self.model.conv_activation)
            max_val = np.max(self.model.conv_activation)
            self.activation_stats['conv'] = (min_val, max_val)
        
        # 收集全连接层输入统计
        if self.model.fc_input is not None:
            min_val = np.min(self.model.fc_input)
            max_val = np.max(self.model.fc_input)
            self.activation_stats['fc'] = (min_val, max_val)
        
        print(f"Collected stats - Conv: {self.activation_stats.get('conv', 'N/A')}, "
              f"FC: {self.activation_stats.get('fc', 'N/A')}")
    
    def compute_quant_params(self, layer_name, num_bits=8):
        """计算量化参数"""
        if layer_name not in self.activation_stats:
            raise ValueError(f"No stats for layer {layer_name}")
        
        min_val, max_val = self.activation_stats[layer_name]
        
        # 对称量化（zero_point=0）
        if min_val >= 0:  # 适用于ReLU后的激活
            scale = (max_val) / (2**(num_bits-1) - 1)
            zero_point = 0
        else:  # 非对称量化
            scale = (max_val - min_val) / (2**(num_bits-1) - 1)
            zero_point = np.round(-min_val / scale).astype(np.int32)
            zero_point = max(0, min(zero_point, 2**(num_bits-1)-1))  # 限制范围
        
        return scale, zero_point

# ======================
# 3. 量化工具函数
# ======================
def quantize_tensor(tensor, scale, zero_point, num_bits=8):
    """将浮点张量量化为整数"""
    q_min = 0 if zero_point == 0 else -2**(num_bits-1)
    q_max = 2**(num_bits-1) - 1
    
    # 量化公式: quantized = round(tensor/scale + zero_point)
    quantized = np.round(tensor / scale + zero_point)
    quantized = np.clip(quantized, q_min, q_max).astype(np.int8)
    return quantized

def dequantize_tensor(quantized, scale, zero_point):
    """将量化张量反量化为浮点"""
    return (quantized.astype(np.float32) - zero_point) * scale

# ======================
# 4. 量化推理实现
# ======================
def quantized_forward(model, x, conv_scale, conv_zero_point, fc_scale, fc_zero_point, num_bits=8):
    """量化推理流程"""
    # 1. 量化输入（假设输入已预处理）
    # 这里简化处理，实际应用中需要对输入做量化
    
    # 2. 量化卷积层
    conv_out = model.conv_forward(x)
    quantized_conv = quantize_tensor(conv_out, conv_scale, conv_zero_point, num_bits)
    dequantized_conv = dequantize_tensor(quantized_conv, conv_scale, conv_zero_point)
    
    # 3. ReLU激活
    relu_out = np.maximum(dequantized_conv, 0)
    
    # 4. 展平
    flattened, _ = model.flatten(relu_out)
    
    # 5. 量化全连接层输入
    quantized_fc_input = quantize_tensor(flattened, fc_scale, fc_zero_point, num_bits)
    dequantized_fc_input = dequantize_tensor(quantized_fc_input, fc_scale, fc_zero_point)
    
    # 6. 全连接层计算
    fc_out = dequantized_fc_input @ model.fc_weights + model.fc_bias
    
    # 7. Softmax
    probs = model.softmax(fc_out)
    return probs

# ======================
# 5. 完整测试流程
# ======================
if __name__ == "__main__":
    # 1. 初始化模型
    model = CNNWithSoftmax(in_channels=3, out_channels=16, input_size=28)
    
    # 2. 创建校准器并收集数据
    calibrator = PTQCalibrator(model)
    calibration_data = np.random.randn(10, 3, 28, 28)  # 模拟校准数据
    calibrator.collect_statistics(calibration_data)
    
    # 3. 计算量化参数
    conv_scale, conv_zero_point = calibrator.compute_quant_params('conv', num_bits=8)
    fc_scale, fc_zero_point = calibrator.compute_quant_params('fc', num_bits=8)
    print(f"Conv Quant Params - Scale: {conv_scale:.4f}, Zero Point: {conv_zero_point}")
    print(f"FC Quant Params - Scale: {fc_scale:.4f}, Zero Point: {fc_zero_point}")
    
    # 4. 测试量化推理
    test_input = np.random.randn(1, 3, 28, 28)
    original_output = model.forward(test_input)  # 浮点推理
    quantized_output = quantized_forward(
        model, test_input, conv_scale, conv_zero_point, 
        fc_scale, fc_zero_point, num_bits=8
    )  # 量化推理
    
    # 5. 比较结果
    print("\nOriginal Output (softmax):", original_output[0])
    print("Quantized Output (softmax):", quantized_output[0])
    print("Max Difference:", np.max(np.abs(original_output - quantized_output)))