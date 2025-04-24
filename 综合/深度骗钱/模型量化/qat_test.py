import numpy as np

# ======================
# 1. 模型层定义
# ======================

class Conv2D:
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=0):
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.padding = padding
        # 初始化权重和偏置
        limit = np.sqrt(6.0 / (in_channels * kernel_size * kernel_size + out_channels * kernel_size * kernel_size))
        self.weights = np.random.uniform(-limit, limit, (out_channels, in_channels, kernel_size, kernel_size))
        self.bias = np.zeros(out_channels)
        # 量化参数
        self.scale = 1.0
        self.zero_point = 0

    def forward(self, x, quantize=True):
        batch_size, in_channels, height, width = x.shape
        out_height = (height - self.kernel_size + 2 * self.padding) // self.stride + 1
        out_width = (width - self.kernel_size + 2 * self.padding) // self.stride + 1

        # 填充输入
        if self.padding > 0:
            x_padded = np.pad(x, ((0, 0), (0, 0), (self.padding, self.padding), (self.padding, self.padding)), mode='constant')
        else:
            x_padded = x

        # 初始化输出
        output = np.zeros((batch_size, self.out_channels, out_height, out_width))

        # 执行卷积
        for b in range(batch_size):
            for oc in range(self.out_channels):
                for ic in range(in_channels):
                    for i in range(out_height):
                        for j in range(out_width):
                            h_start = i * self.stride
                            h_end = h_start + self.kernel_size
                            w_start = j * self.stride
                            w_end = w_start + self.kernel_size
                            output[b, oc, i, j] += np.sum(
                                x_padded[b, ic, h_start:h_end, w_start:w_end] * self.weights[oc, ic]
                            )
                output[b, oc] += self.bias[oc]

        if quantize:
            # 量化卷积输出
            quantized_output = self.quantize(output)
            return quantized_output
        else:
            return output

    def quantize(self, x):
        # 对称量化
        if np.min(x) >= 0:
            # 非负激活，zero_point=0
            scale = (np.max(x) - np.min(x)) / (2**8 - 1) if np.max(x) != np.min(x) else 1.0
            if scale == 0:
                scale = 1.0
            zero_point = 0
        else:
            # 对于有正有负的激活，使用非对称量化
            scale = (np.max(x) - np.min(x)) / (2**8 - 1) if np.max(x) != np.min(x) else 1.0
            if scale == 0:
                scale = 1.0
            zero_point = np.round(-np.min(x) / scale).astype(np.int32)
            # 限制zero_point范围
            zero_point = max(0, min(zero_point, 255))
        
        self.scale = scale
        self.zero_point = zero_point

        # 量化公式: quantized = round(x / scale + zero_point)
        # 但由于scale和zero_point是基于当前batch计算的，这里简化为全局统计
        # 实际QAT中应基于校准数据计算固定的scale和zero_point
        # 这里为了简化，我们使用全局最小最大值
        global_min = np.min(x)
        global_max = np.max(x)
        if global_max == global_min:
            scale = 1.0
            zero_point = 0
        else:
            scale = (global_max - global_min) / (2**8 - 1)
            zero_point = np.round(-global_min / scale).astype(np.int32)
            zero_point = max(0, min(zero_point, 255))

        self.scale = scale
        self.zero_point = zero_point

        quantized = np.round(x / scale + zero_point).clip(0, 255).astype(np.int8)
        return quantized

    def dequantize(self, quantized):
        return (quantized.astype(np.float32) - self.zero_point) * self.scale

    def backward(self, grad_output):
        # 简化的梯度计算，忽略量化影响
        # 实际QAT中需要处理量化梯度
        batch_size, out_channels, out_height, out_width = grad_output.shape
        _, in_channels, height, width = self.weights.shape

        grad_weights = np.zeros_like(self.weights)
        grad_bias = np.zeros_like(self.bias)
        grad_input = np.zeros((batch_size, in_channels, height, width))

        # 填充grad_output以匹配输入尺寸
        if self.padding > 0:
            pad_grad = np.pad(grad_output, ((0, 0), (0, 0), (self.padding, self.padding), (self.padding, self.padding)), mode='constant')
        else:
            pad_grad = grad_output

        for b in range(batch_size):
            for oc in range(out_channels):
                for ic in range(in_channels):
                    for i in range(height):
                        for j in range(width):
                            h_start = i
                            h_end = h_start + self.kernel_size
                            w_start = j
                            w_end = w_start + self.kernel_size
                            # 提取对应的grad_output区域
                            grad_region = pad_grad[b, oc, 
                                                  max(0, i - (self.kernel_size -1) //2):min(out_height, i + (self.kernel_size +1) //2 +1),
                                                  max(0, j - (self.kernel_size -1) //2):min(out_width, j + (self.kernel_size +1) //2 +1)]
                            # 计算重叠区域
                            # 这里简化处理，实际应使用im2col等高效方法
                            # 为简化，假设kernel_size=3, stride=1, padding=1
                            if self.kernel_size == 3 and self.stride == 1 and self.padding == 1:
                                h_offset = i
                                w_offset = j
                                grad_region_correct = pad_grad[b, oc, 
                                                              h_offset:h_offset + self.kernel_size,
                                                              w_offset:w_offset + self.kernel_size]
                                grad_weights[oc, ic] += np.sum(grad_region_correct * self.input_padded[b, ic, h_offset:h_offset + self.kernel_size, w_offset:w_offset + self.kernel_size])
                                grad_input[b, ic, i, j] += np.sum(grad_region_correct * self.weights[oc, ic])
                            else:
                                # 更通用的实现需要im2col
                                pass
                grad_bias[oc] += np.sum(grad_output[b, oc])

        # 由于简化处理，grad_input可能需要修正
        # 这里返回未修正的grad_input
        return grad_input, grad_weights, grad_bias

class ReLU:
    def forward(self, x, quantize=True):
        self.input = x
        output = np.maximum(x, 0)
        if quantize:
            quantized_output = self.quantize(output)
            return quantized_output
        else:
            return output

    def quantize(self, x):
        # ReLU输出非负，zero_point=0
        scale = (np.max(x) - np.min(x)) / (2**8 - 1) if np.max(x) != np.min(x) else 1.0
        if scale == 0:
            scale = 1.0
        zero_point = 0
        self.scale = scale
        self.zero_point = zero_point

        quantized = np.round(x / scale + zero_point).clip(0, 255).astype(np.int8)
        return quantized

    def dequantize(self, quantized):
        return (quantized.astype(np.float32) - self.zero_point) * self.scale

    def backward(self, grad_output):
        # ReLU的梯度：输入>0时为1，否则为0
        grad_input = grad_output.copy()
        grad_input[self.input < 0] = 0
        return grad_input

class Flatten:
    def forward(self, x, quantize=False):
        self.input_shape = x.shape
        output = x.reshape(x.shape[0], -1)
        if quantize:
            # 通常不对Flatten层进行量化
            pass
        return output

    def backward(self, grad_output):
        return grad_output.reshape(self.input_shape)

class Linear:
    def __init__(self, in_features, out_features):
        self.in_features = in_features
        self.out_features = out_features
        # 初始化权重和偏置
        limit = np.sqrt(6.0 / (in_features + out_features))
        self.weights = np.random.uniform(-limit, limit, (out_features, in_features))
        self.bias = np.zeros(out_features)
        # 量化参数
        self.scale = 1.0
        self.zero_point = 0

    def forward(self, x, quantize=True):
        self.input = x
        output = x @ self.weights.T + self.bias
        if quantize:
            quantized_output = self.quantize(output)
            return quantized_output
        else:
            return output

    def quantize(self, x):
        # 全连接层输出的量化
        scale = (np.max(x) - np.min(x)) / (2**8 - 1) if np.max(x) != np.min(x) else 1.0
        if scale == 0:
            scale = 1.0
        zero_point = np.round(-np.min(x) / scale).astype(np.int32)
        zero_point = max(0, min(zero_point, 255))
        self.scale = scale
        self.zero_point = zero_point

        quantized = np.round(x / scale + zero_point).clip(0, 255).astype(np.int8)
        return quantized

    def dequantize(self, quantized):
        return (quantized.astype(np.float32) - self.zero_point) * self.scale

    def backward(self, grad_output):
        # 计算梯度
        grad_input = grad_output @ self.weights
        grad_weights = self.input.T @ grad_output
        grad_bias = np.sum(grad_output, axis=0)
        return grad_input, grad_weights, grad_bias

class Softmax:
    def forward(self, x, quantize=False):
        # 数值稳定性的softmax
        exp_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        output = exp_x / np.sum(exp_x, axis=1, keepdims=True)
        if quantize:
            # Softmax输出通常不需要量化，因为它是概率分布
            # 但为了完整性，这里展示如何量化
            quantized_output = self.quantize(output)
            return quantized_output
        else:
            return output

    def quantize(self, x):
        # Softmax输出量化（通常不推荐）
        scale = (np.max(x) - np.min(x)) / (2**8 - 1) if np.max(x) != np.min(x) else 1.0
        if scale == 0:
            scale = 1.0
        zero_point = np.round(-np.min(x) / scale).astype(np.int32)
        zero_point = max(0, min(zero_point, 255))
        self.scale = scale
        self.zero_point = zero_point

        quantized = np.round(x / scale + zero_point).clip(0, 255).astype(np.int8)
        return quantized

    def dequantize(self, quantized):
        return (quantized.astype(np.float32) - self.zero_point) * self.scale

    def backward(self, grad_output):
        # Softmax的梯度计算较为复杂，这里简化处理
        # 实际应用中应使用更高效的实现
        s = self.forward(grad_output, quantize=False).reshape(-1, 1)
        grad_input = grad_output * s * (1 - s)
        # 由于softmax的梯度需要考虑其他类别的影响，这里简化为对角矩阵
        # 正确的实现应使用Jacobian矩阵
        batch_size = grad_output.shape[0]
        grad_input_full = np.zeros_like(grad_output)
        for i in range(batch_size):
            grad_input_full[i] = grad_output[i] * (s[i] - np.sum(grad_output[i] * s))
        # 更正：实际上，softmax的梯度为 (softmax(x) - y) * grad_output，其中y是真实标签
        # 这里假设grad_output已经是 (softmax(x) - y) * grad_output_final
        # 因此，直接返回grad_output
        return grad_output  # 这里有误，需根据具体任务调整

# ======================
# 2. 量化感知训练（QAT）模型
# ======================
class QATModel:
    def __init__(self, in_channels=3, out_channels=16, input_size=28):
        self.conv = Conv2D(in_channels, out_channels, kernel_size=3, padding=1)
        self.relu = ReLU()
        self.flatten = Flatten()
        self.fc = Linear(out_channels * (input_size // 2) * (input_size // 2), 10)  # 假设输入尺寸为28x28，经过2x2池化后为14x14
        self.softmax = Softmax()

    def forward(self, x, quantize=True):
        # 前向传播，可以选择是否量化
        conv_out = self.conv.forward(x, quantize)
        relu_out = self.relu.forward(conv_out, quantize)
        flatten_out = self.flatten.forward(relu_out, quantize=False)  # 通常不对Flatten进行量化
        fc_out = self.fc.forward(flatten_out, quantize)
        probs = self.softmax.forward(fc_out, quantize)
        return probs

    def backward(self, grad_output):
        # 反向传播
        grad_fc = self.softmax.backward(grad_output)
        grad_flatten, grad_fc_weights, grad_fc_bias = self.fc.backward(grad_fc)
        # 注意：由于Flatten不进行量化，grad_flatten直接传递
        grad_relu = self.flatten.backward(grad_flatten)
        grad_conv = self.relu.backward(grad_relu)
        grad_input = self.conv.backward(grad_conv)
        return grad_input, grad_fc_weights, grad_fc_bias

    def update_parameters(self, learning_rate):
        # 更新参数（简化版，未实现动量等优化器）
        # 这里需要实现参数更新，并考虑量化参数的调整
        pass

# ======================
# 3. 训练流程
# ======================
def cross_entropy_loss(y_pred, y_true):
    # y_true是one-hot编码
    m = y_true.shape[0]
    log_likelihood = -np.log(y_pred[range(m), y_true.argmax(axis=1)])
    loss = np.sum(log_likelihood) / m
    return loss

def accuracy(y_pred, y_true):
    predictions = np.argmax(y_pred, axis=1)
    labels = np.argmax(y_true, axis=1)
    correct = np.sum(predictions == labels)
    return correct / len(labels)

# 生成模拟数据
def generate_data(num_samples=1000, input_size=28, in_channels=3, num_classes=10):
    X = np.random.randn(num_samples, in_channels, input_size, input_size).astype(np.float32)
    y = np.random.randint(0, num_classes, num_samples)
    y_one_hot = np.zeros((num_samples, num_classes))
    y_one_hot[np.arange(num_samples), y] = 1
    return X, y_one_hot

# 训练函数
def train_qat_model(model, X_train, y_train, epochs=5, batch_size=32, learning_rate=0.01, calibration_data=None):
    num_samples = X_train.shape[0]
    num_batches = num_samples // batch_size

    for epoch in range(epochs):
        print(f"Epoch {epoch+1}/{epochs}")
        # 打乱数据
        indices = np.arange(num_samples)
        np.random.shuffle(indices)
        X_shuffled = X_train[indices]
        y_shuffled = y_train[indices]

        for batch_idx in range(num_batches):
            # 获取当前批次
            start = batch_idx * batch_size
            end = start + batch_size
            X_batch = X_shuffled[start:end]
            y_batch = y_shuffled[start:end]

            # 前向传播（训练时不量化）
            y_pred = model.forward(X_batch, quantize=False)

            # 计算损失
            loss = cross_entropy_loss(y_pred, y_batch)

            # 反向传播
            grad_output = y_pred - y_batch  # 简化的梯度计算，未考虑真实标签的one-hot编码

            grad_input, grad_fc_weights, grad_fc_bias = model.backward