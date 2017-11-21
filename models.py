import sys
import torch
import torch.nn as nn
import torchvision.models as models
import torch.nn.functional as F
from torch.autograd import Variable


class EncoderCNN(nn.Module):
    def __init__(self, emb_dim):
        '''
        Load the pretrained ResNet152 and replace fc
        '''
        super(EncoderCNN, self).__init__()
        resnet = models.resnet152(pretrained=True)
        modules = list(resnet.children())[:-1]
        self.resnet = nn.Sequential(*modules)
        self.A = nn.Linear(resnet.fc.in_features, emb_dim)

    def forward(self, images):
        '''Extract the image feature vectors'''
        features = self.resnet(images)
        features = Variable(features.data)
        features = features.view(features.size(0), -1)
        features = self.A(features)
        return features


class FactoredLSTM(nn.Module):
    def __init__(self, emb_dim, hidden_dim, factored_dim,  vocab_size):
        super(FactoredLSTM, self).__init__()
        self.hidden_dim = hidden_dim
        self.vocab_size = vocab_size

        # embedding
        self.B = nn.Embedding(vocab_size, emb_dim)

        # factored lstm weights
        self.U_i = nn.Linear(factored_dim, hidden_dim)
        self.S_fi = nn.Linear(factored_dim, factored_dim)
        self.V_i = nn.Linear(emb_dim, factored_dim)
        self.W_i = nn.Linear(hidden_dim, hidden_dim)

        self.U_f = nn.Linear(factored_dim, hidden_dim)
        self.S_ff = nn.Linear(factored_dim, factored_dim)
        self.V_f = nn.Linear(emb_dim, factored_dim)
        self.W_f = nn.Linear(hidden_dim, hidden_dim)

        self.U_o = nn.Linear(factored_dim, hidden_dim)
        self.S_fo = nn.Linear(factored_dim, factored_dim)
        self.V_o = nn.Linear(emb_dim, factored_dim)
        self.W_o = nn.Linear(hidden_dim, hidden_dim)

        self.U_c = nn.Linear(factored_dim, hidden_dim)
        self.S_fc = nn.Linear(factored_dim, factored_dim)
        self.V_c = nn.Linear(emb_dim, factored_dim)
        self.W_c = nn.Linear(hidden_dim, hidden_dim)

        self.S_hi = nn.Linear(factored_dim, factored_dim)
        self.S_hf = nn.Linear(factored_dim, factored_dim)
        self.S_ho = nn.Linear(factored_dim, factored_dim)
        self.S_hc = nn.Linear(factored_dim, factored_dim)

        # self.S_ri = nn.Linear(factored_dim, factored_dim)
        # self.S_rf = nn.Linear(factored_dim, factored_dim)
        # self.S_ro = nn.Linear(factored_dim, factored_dim)
        # self.S_rc = nn.Linear(factored_dim, factored_dim)

        # weight for output
        self.C = nn.Linear(hidden_dim, vocab_size)

    def forward_step(self, embedded, h_0, c_0, mode):
        i = self.V_i(embedded)
        f = self.V_f(embedded)
        o = self.V_o(embedded)
        c = self.V_c(embedded)

        if mode == "factual":
            i = self.S_fi(i)
            f = self.S_ff(f)
            o = self.S_fo(o)
            c = self.S_fc(c)
        elif mode == "humorous":
            i = self.S_hi(i)
            f = self.S_hf(f)
            o = self.S_ho(o)
            c = self.S_hc(c)
        # elif mode == "romantic":
        #     i = self.S_ri(i)
        #     f = self.S_rf(f)
        #     o = self.S_ro(o)
        #     c = self.S_rc(c)
        else:
            sys.stderr.write("mode name wrong!")

        i_t = F.sigmoid(self.U_i(i) + self.W_i(h_0))
        f_t = F.sigmoid(self.U_f(f) + self.W_f(h_0))
        o_t = F.sigmoid(self.U_o(o) + self.W_o(h_0))
        c_tilda = F.tanh(self.U_c(c) + self.W_c(h_0))

        c_t = f_t * c_0 + i_t * c_tilda
        h_t = o_t * c_t

        outputs = self.C(h_t)

        return outputs, h_t, c_t

    def forward(self, captions, features=None, mode="factual"):
        '''
        Args:
            features: fixed vectors from images, [batch, emb_dim]
            captions: [batch, max_len]
            mode: type of caption to generate
        '''
        batch_size = captions.size(0)
        embedded = self.B(captions)  # [batch, max_len, emb_dim]
        # concat features and captions
        if mode == "factual":
            if features is None:
                sys.stderr.write("features is None!")
            embedded = torch.cat((features.unsqueeze(1), embedded), 1)

        # initialize hidden state
        h_t = Variable(torch.zeros(batch_size, self.hidden_dim))
        c_t = Variable(torch.zeros(batch_size, self.hidden_dim))

        if torch.cuda.is_available():
            h_t = h_t.cuda()
            c_t = c_t.cuda()

        all_outputs = []
        # iterate
        for ix in range(embedded.size(1) - 1):
            emb = embedded[:, ix, :]
            outputs, h_t, c_t = self.forward_step(emb, h_t, c_t, mode=mode)
            all_outputs.append(outputs)

        all_outputs = torch.stack(all_outputs, 1)

        return all_outputs