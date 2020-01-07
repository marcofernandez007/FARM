# fmt: off
import logging
import pprint
import json

from farm.data_handler.data_silo import DataSilo
from farm.data_handler.processor import SquadProcessor, BertStyleLMProcessor
from farm.modeling.optimization import initialize_optimizer
from farm.infer import Inferencer
from farm.modeling.adaptive_model import AdaptiveModel
from farm.modeling.prediction_head import QuestionAnsweringHead, BertLMHead, NextSentenceHead
from farm.modeling.language_model import LanguageModel, Bert
from farm.modeling.tokenization import Tokenizer
from farm.train import Trainer
from farm.utils import set_all_seeds, MLFlowLogger, initialize_device_settings
from transformers.modeling_bert import BertModel, BertConfig
from transformers.tokenization_bert import BertTokenizer


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)

ml_logger = MLFlowLogger(tracking_uri="")
ml_logger.init_experiment(experiment_name="from_scratch", run_name="debug")

#########################
######## Settings
########################
set_all_seeds(seed=39)
device, n_gpu = initialize_device_settings(use_cuda=True)
learning_rate = 1e-6
batch_size = 32
max_seq_len = 128
n_epochs = 10
evaluate_every = 63
vocab_size = 30000
# dev_filename = None
save_dir = "../saved_models/from_scratch"
predictions_file = save_dir + "/predictions.json"
full_predictions_file = save_dir + "/full_predictions.json"
inference_multiprocessing = True
train = True
inference = True

if train:
    # 1.Create a tokenizer
    tokenizer = BertTokenizer("../saved_models/airbert_2.3.0/vocab.txt")

    # 2. Create a DataProcessor that handles all the conversion from raw text into a pytorch Dataset
    processor = BertStyleLMProcessor(
        data_dir="../data/lm_finetune_nips",
        tokenizer=tokenizer, max_seq_len=max_seq_len,
        train_filename="train_small.txt",
        dev_filename="train_small.txt",
        test_filename=None
        )

    # 3. Create a DataSilo that loads several datasets (train/dev/test), provides DataLoaders for them and calculates a few descriptive statistics of our datasets
    data_silo = DataSilo(processor=processor, batch_size=batch_size, distributed=False)

    # 4. Create an AdaptiveModel
    # a) which consists of a pretrained language model as a basis
    language_model = LanguageModel.from_scratch("bert", vocab_size)

    # b) and *two* prediction heads on top that are suited for our task => Language Model finetuning
    lm_prediction_head = BertLMHead(768, vocab_size)
    next_sentence_head = NextSentenceHead([768, 2], task_name="nextsentence")

    model = AdaptiveModel(
        language_model=language_model,
        prediction_heads=[lm_prediction_head, next_sentence_head],
        embeds_dropout_prob=0.1,
        lm_output_types=["per_token", "per_sequence"],
        device=device,)

    # 5. Create an optimizer
    optimizer, warmup_linear = initialize_optimizer(
        model=model,
        learning_rate=learning_rate,
        warmup_proportion=0.1,
        n_batches=len(data_silo.loaders["train"]),
        n_epochs=n_epochs,
    )
    # 6. Feed everything to the Trainer, which keeps care of growing our model and evaluates it from time to time
    trainer = Trainer(
        optimizer=optimizer,
        data_silo=data_silo,
        epochs=n_epochs,
        n_gpu=n_gpu,
        warmup_linear=warmup_linear,
        evaluate_every=evaluate_every,
        device=device,
    )
    # 7. Let it grow! Watch the tracked metrics live on the public mlflow server: https://public-mlflow.deepset.ai
    model = trainer.train(model)

    # 8. Hooray! You have a model. Store it:
    model.save(save_dir)
    processor.save(save_dir)


# if inference:
#     model = Inferencer.load(save_dir, batch_size=batch_size, gpu=True)
#     full_result = model.inference_from_file(file=inference_file,
#                                             use_multiprocessing=inference_multiprocessing)
#
#     for x in full_result:
#         print(x)
#         print()
#
#     result = {r["id"]: r["preds"][0][0] for r in full_result}
#     full_result =  {r["id"]: r["preds"] for r in full_result}
#
#     json.dump(result,
#               open(predictions_file, "w"),
#               indent=4,
#               ensure_ascii=False)
#     json.dump(full_result,
#               open(full_predictions_file, "w"),
#               indent=4,
#               ensure_ascii=False)
#
