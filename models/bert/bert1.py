import pandas as pd
import torch
from transformers import CamembertTokenizer, CamembertForSequenceClassification, AdamW
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from tqdm import tqdm

# Load training data
training_data = 'https://raw.githubusercontent.com/thebrisly/UNIL_Geneva_DSML/main/data/training_data.csv'
train_df = pd.read_csv(training_data, encoding='utf-8')
train_df['difficulty'] = train_df['difficulty'].replace(['A1', 'A2', 'B1', 'B2', 'C1', 'C2'], [0, 1, 2, 3, 4, 5])

# Load test data
test_data = 'https://raw.githubusercontent.com/thebrisly/UNIL_Geneva_DSML/main/data/unlabelled_test_data.csv'
test_df = pd.read_csv(test_data)

# Tokenization and padding
tokenizer = CamembertTokenizer.from_pretrained('camembert/camembert-large', do_lower_case=True)

epochs = 6
MAX_LEN = 64
batch_size = 16
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def tokenize_sentences(sentences, max_len=64):
    input_ids = []
    attention_masks = []

    for sent in tqdm(sentences, desc="Tokenizing sentences"):
        encoded_dict = tokenizer.encode_plus(
            sent,
            add_special_tokens=True,
            max_length=max_len,
            pad_to_max_length=True,
            return_attention_mask=True,
            return_tensors='pt',
        )

        input_ids.append(encoded_dict['input_ids'])
        attention_masks.append(encoded_dict['attention_mask'])

    input_ids = torch.cat(input_ids, dim=0)
    attention_masks = torch.cat(attention_masks, dim=0)

    return input_ids, attention_masks

# Tokenize training data
train_input_ids, train_attention_masks = tokenize_sentences(train_df['sentence'], max_len=MAX_LEN)
labels = torch.tensor(train_df['difficulty'].values)

# Split the data
train_inputs, validation_inputs, train_labels, validation_labels, train_masks, validation_masks = train_test_split(
    train_input_ids, labels, train_attention_masks, random_state=42, test_size=0.2
)

# Define DataLoader for training and validation data
train_data = TensorDataset(train_inputs, train_masks, train_labels)
train_sampler = RandomSampler(train_data)
train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=batch_size)

validation_data = TensorDataset(validation_inputs, validation_masks, validation_labels)
validation_sampler = SequentialSampler(validation_data)
validation_dataloader = DataLoader(validation_data, sampler=validation_sampler, batch_size=batch_size)

# Model configuration
model = CamembertForSequenceClassification.from_pretrained("camembert/camembert-large", num_labels=6, dropout=0.1)

# Training parameters
epochs = 6
lr = 2e-5
optimizer = AdamW(model.parameters(), lr=lr)

# Training loop
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

for epoch in range(epochs):
    model.train()
    total_loss = 0

    for batch in tqdm(train_dataloader, desc=f"Epoch {epoch + 1} training"):
        input_ids, attention_mask, label = batch
        input_ids, attention_mask, label = input_ids.to(device), attention_mask.to(device), label.to(device)

        optimizer.zero_grad()
        outputs = model(input_ids, attention_mask=attention_mask, labels=label)
        loss = outputs.loss
        total_loss += loss.item()

        loss.backward()
        optimizer.step()

    avg_train_loss = total_loss / len(train_dataloader)

    # Validation
    model.eval()
    val_loss = 0

    for batch in tqdm(validation_dataloader, desc=f"Epoch {epoch + 1} validation"):
        input_ids, attention_mask, label = batch
        input_ids, attention_mask, label = input_ids.to(device), attention_mask.to(device), label.to(device)

        with torch.no_grad():
            outputs = model(input_ids, attention_mask=attention_mask, labels=label)

        loss = outputs.loss
        val_loss += loss.item()

    avg_val_loss = val_loss / len(validation_dataloader)
    print(f"Epoch {epoch + 1}: Avg Training Loss={avg_train_loss}, Avg Validation Loss={avg_val_loss}")

# Apply the model to the unlabelled test data
test_input_ids, test_attention_masks = tokenize_sentences(test_df['sentence'], max_len=MAX_LEN)
test_dataset = TensorDataset(test_input_ids, test_attention_masks)
test_dataloader = DataLoader(test_dataset, batch_size=batch_size)

model.eval()
predictions = []

for batch in tqdm(test_dataloader, desc="Predicting on test data"):
    input_ids, attention_mask = batch
    input_ids, attention_mask = input_ids.to(device), attention_mask.to(device)

    with torch.no_grad():
        outputs = model(input_ids, attention_mask=attention_mask)

    logits = outputs.logits
    preds = torch.argmax(logits, dim=1).cpu().numpy()
    predictions.extend(preds)

# Convert predictions to difficulty levels
difficulty_levels = {0: 'A1', 1: 'A2', 2: 'B1', 3: 'B2', 4: 'C1', 5: 'C2'}
predicted_difficulties = [difficulty_levels[p] for p in predictions]

# Create a submission dataframe
submission_df = pd.DataFrame({'id': test_df['id'], 'difficulty': predicted_difficulties})

# Save the submission dataframe to a CSV file
submission_df.to_csv('submission.csv', index=False)
