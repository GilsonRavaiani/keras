from keras.preprocessing.text import Tokenizer, one_hot
import pytest
import numpy as np


def test_one_hot():
    text = 'The cat sat on the mat.'
    encoded = one_hot(text, 5)
    assert len(encoded) == 6
    assert np.max(encoded) <= 4
    assert np.min(encoded) >= 0


def test_tokenizer():
    texts = ['The cat sat on the mat.',
             'The dog sat on the log.',
             'Dogs and cats living together.']
    tokenizer = Tokenizer(num_words=10)
    tokenizer.fit_on_texts(texts)

    sequences = []
    for seq in tokenizer.texts_to_sequences_generator(texts):
        sequences.append(seq)
    assert np.max(np.max(sequences)) <= 10
    assert np.min(np.min(sequences)) == 1

    tokenizer.fit_on_sequences(sequences)

    for mode in ['binary', 'count', 'tfidf', 'freq']:
        matrix = tokenizer.texts_to_matrix(texts, mode)


def test_tokenizer_one_word():
    texts = ['I am',
             'I was']
    tokenizer = Tokenizer(num_words=1)
    tokenizer.fit_on_texts(texts)

    sequences = tokenizer.texts_to_sequences(texts)

    # both should only contain the token for the word "I"
    np.testing.assert_array_equal(sequences[0], np.asarray([1]))
    np.testing.assert_array_equal(sequences[1], np.asarray([1]))


def test_tokenizer_with_oov_one_word():
    texts = ['I am',
             'I was']
    tokenizer = Tokenizer(num_words=1, use_oov_token=True)
    tokenizer.fit_on_texts(texts)

    sequences = tokenizer.texts_to_sequences(texts)

    np.testing.assert_array_equal(sequences[0], np.asarray([1, 2]))
    np.testing.assert_array_equal(sequences[1], np.asarray([1, 2]))


def test_tokenizer_with_oov_more_words():
    texts = ['I am who I am',
             'I was who I am']
    tokenizer = Tokenizer(num_words=3, use_oov_token=True)
    tokenizer.fit_on_texts(texts)

    sequences = tokenizer.texts_to_sequences(texts)

    assert len(sequences[0]) == 5
    assert len(sequences[1]) == 5

    assert np.max(sequences) == 4
    assert np.min(sequences) == 1


if __name__ == '__main__':
    pytest.main([__file__])
