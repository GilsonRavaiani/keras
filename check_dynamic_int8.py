import time

import jax
import numpy as np
import tensorflow as tf

import keras
from keras import backend
from keras import layers
from keras import models
from keras import ops
from keras import saving

# Model / data parameters
num_classes = 10
input_shape = (28, 28, 1)
epochs = 1

# Load the data and split it between train and test sets
(x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
x_train = x_train.astype("float32") / 255
x_test = x_test.astype("float32") / 255
x_train = np.expand_dims(x_train, -1)
x_test = np.expand_dims(x_test, -1)
y_train = keras.utils.to_categorical(y_train, num_classes)
y_test = keras.utils.to_categorical(y_test, num_classes)


def build_model(num_layers=32, units=1024):
    inputs = layers.Input([28, 28])
    x = layers.Flatten()(inputs)
    for _ in range(num_layers):
        x = layers.Dense(units)(x)
        x = layers.BatchNormalization()(x)
        x = layers.ReLU()(x)
    outputs = layers.Dense(10, use_bias=True, activation="softmax")(x)
    model = models.Model(inputs, outputs)
    return model


def enable_lora(model):
    for layer in model.layers:
        if hasattr(layer, "enable_lora"):
            layer.enable_lora(2)


def benchmark(model, batch_size=1024, input_shape=(28, 28), iterations=200):
    def fn(x):
        return model(x, training=False)

    if backend.backend() == "tensorflow":
        jit_fn = tf.function(fn, jit_compile=True)
    elif backend.backend() == "jax":
        jit_fn = jax.jit(fn)
    else:
        jit_fn = fn

    # warmup
    x = ops.ones([batch_size, *input_shape])
    for _ in range(10):
        _ = ops.convert_to_numpy(jit_fn(x))

    times = []
    for _ in range(iterations):
        t0 = time.time()
        _ = ops.convert_to_numpy(jit_fn(x))
        t1 = time.time()
        times.append(t1 - t0)
    avg_time = sum(times) / len(times)
    return avg_time


ENABLE_LORA = False

model = build_model(num_layers=32, units=1024)
model.compile(
    loss="categorical_crossentropy", optimizer="adam", metrics=["accuracy"]
)

"""Train float model"""
print("Start training:")
model.fit(x_train, y_train, batch_size=128, epochs=epochs, validation_split=0.1)
print("Performance of float32:")
score = model.evaluate(x_test, y_test, verbose=0)
print(f"Test accuracy: {score[1]:.5f}")
avg_time = benchmark(model)
print(f"Avg. time (batch_size=1024): {avg_time:.5f}s")
model.save("model_fp32.keras")

if ENABLE_LORA:
    """Enable lora"""
    enable_lora(model)

    """Fine-tuning lora weights with trainable quantization"""
    model.compile(
        loss="categorical_crossentropy", optimizer="adam", metrics=["accuracy"]
    )
    model.fit(
        x_train, y_train, batch_size=128, epochs=epochs, validation_split=0.1
    )
    print("Performance of fine-tuning lora with trainable quantization:")
    score = model.evaluate(x_test, y_test, verbose=0)
    print(f"Test accuracy: {score[1]:.5f}")
    avg_time = benchmark(model)
    print(f"Avg. time (batch_size=1024): {avg_time:.5f}s")

    """Quantize to int8 weights"""
    model.quantize(mode="dynamic_int8")
    int8_model = model
    int8_model.compile(loss="categorical_crossentropy", metrics=["accuracy"])
    score = int8_model.evaluate(x_test, y_test, verbose=0)
    print(f"Test accuracy: {score[1]:.5f}")
    avg_time = benchmark(int8_model)
    print(f"Avg. time (batch_size=1024): {avg_time:.5f}s")
else:
    """Quantization"""
    model.quantize(mode="dynamic_int8")
    int8_model = model
    int8_model.compile(loss="categorical_crossentropy", metrics=["accuracy"])
    score = int8_model.evaluate(x_test, y_test, verbose=0)
    print(f"Test accuracy: {score[1]:.5f}")
    avg_time = benchmark(int8_model)
    print(f"Avg. time (batch_size=1024): {avg_time:.5f}s")

"""Saving & loading"""
int8_model.save("model_int8.keras")
reloaded_int8_model = saving.load_model("model_int8.keras")
reloaded_score = reloaded_int8_model.evaluate(x_test, y_test, verbose=0)
print(f"Reloaded int8 model test accuracy: {reloaded_score[1]:.5f}")
