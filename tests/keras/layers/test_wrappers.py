import pytest
import numpy as np
from numpy.testing import assert_allclose

from keras.layers import wrappers
from keras.layers import core, convolutional
from keras.models import Sequential, model_from_json


def test_TimeDistributed():
    # first, test with Dense layer
    model = Sequential()
    model.add(wrappers.TimeDistributed(core.Dense(2), input_shape=(3, 4)))
    model.add(core.Activation('relu'))

    model.compile(optimizer='rmsprop', loss='mse')
    model.fit(np.random.random((10, 3, 4)), np.random.random((10, 3, 2)), nb_epoch=1, batch_size=10)

    model.get_config()

    # compare to TimeDistributedDense
    test_input = np.random.random((1, 3, 4))
    test_output = model.predict(test_input)
    weights = model.layers[0].get_weights()

    reference = Sequential()
    reference.add(core.TimeDistributedDense(2, input_shape=(3, 4), weights=weights))
    reference.add(core.Activation('relu'))

    reference.compile(optimizer='rmsprop', loss='mse')

    reference_output = reference.predict(test_input)
    assert_allclose(test_output, reference_output, atol=1e-05)

    # nested TimeDistributed wrappers
    model = Sequential()
    model.add(wrappers.TimeDistributed(wrappers.TimeDistributed(core.Dense(input_dim=3, output_dim=5))))
    model.add(wrappers.TimeDistributed(wrappers.TimeDistributed(core.Dense(2))))

    model.compile(optimizer='rmsprop', loss='mse')
    model.train_on_batch(np.random.random((7, 5, 4, 3)), np.random.random((7, 5, 4, 2)))

    model = model_from_json(model.to_json())
    model.summary()

    # test with Convolution2D
    model = Sequential()
    model.add(wrappers.TimeDistributed(convolutional.Convolution2D(5, 2, 2, border_mode='same'), input_shape=(2, 3, 4, 4)))
    model.add(core.Activation('relu'))

    model.compile(optimizer='rmsprop', loss='mse')
    model.train_on_batch(np.random.random((10, 5, 1, 2, 3, 4, 4)), np.random.random((10, 5, 1, 2, 5, 4, 4)))

    model = model_from_json(model.to_json())
    model.summary()
    
if __name__ == '__main__':
    pytest.main([__file__])
