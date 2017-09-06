#import numpy as np
from sklearn.externals import joblib


def compile_feats(logprob, entropy, confidence, cs_logprob, predicted):
    retval = {}
    retval['logprob'] = logprob
    retval['entropy'] = entropy
    retval['confidence'] = confidence
    retval['predicted'] = predicted
    if cs_logprob is not None:
        retval['cs_logprob'] = cs_logprob
    else:
        retval['no_cs_prob'] = True

    return retval


class CS_CNN_chooser:
    def __init__(self, logistic_fn, vectorizer_fn):
        self.cs_cnn_mdl = joblib.load(logistic_fn)
        self.vectorizer = joblib.load(vectorizer_fn)

    def switch_to_CNN(self, feature_dict):
        feats = self.vectorizer.transform([feature_dict])
        #print(feats)
        result = self.cs_cnn_mdl.predict(feats)[0]
        return result
