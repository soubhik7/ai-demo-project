import numpy as np  # linear algebra
import pandas as pd  # data processing, CSV file I/O (e.g. pd.read_csv)
import matplotlib.pyplot as plt

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, models
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.applications import ResNet50
from tensorflow.keras.layers import Input, GlobalAveragePooling2D
from tensorflow.keras.utils import to_categorical
from keras.callbacks import ReduceLROnPlateau


df_train = pd.read_csv(
    "/Users/soubhik/Developer/DataSci&AI/ai-demo-project/data/train.csv"
)
df_test = pd.read_csv(
    "/Users/soubhik/Developer/DataSci&AI/ai-demo-project/data/test.csv"
)

df_train.head(10)
df_train.isnull().sum()

y_train  = df_train['label'].values # np array of all the labels (42000, )
X_train = df_train.drop(columns=['label']).values.reshape(-1,28,28,1)/255.0 # drop the labels and reshape (num_rows, height , width , channel)
X_test = df_test.values.reshape(-1, 28, 28, 1) / 255.0 # /255.0 --> ormalizing these pixel values to the range [0, 1] 


y_train_encoded = to_categorical(y_train, num_classes=10)


fig , axes  = plt.subplots(2, 5, figsize=(12,5))
axes   = axes.flatten()
idx = np.random.randint(0, 42000, size=10)
for i in range(10):
    axes[i].imshow(X_train[idx[i], :].reshape(28,28), cmap='gray')
    axes[i].axis('off') # hide the axes ticks
    axes[i].set_title(str(int(y_train[idx[i]])), color='black', fontsize=25)
plt.show()


model = models.Sequential([
    
    layers.Conv2D(filters=64, kernel_size=3, padding='same', activation='relu', input_shape=(28,28,1)),
    layers.Conv2D(filters=64, kernel_size=3, padding='same',activation='relu'),
    layers.Conv2D(filters=128, kernel_size=3, padding='same',activation='relu'),
    layers.MaxPool2D(pool_size=2),

    layers.Conv2D(filters=128, kernel_size=3, padding='same',activation='relu'),
    layers.Conv2D(filters=192, kernel_size=3, padding='same',activation='relu'),
    layers.MaxPool2D(pool_size=2),
    
    layers.Conv2D(filters=192, kernel_size=5, padding='same',activation='relu'),
    layers.MaxPool2D(pool_size=2, padding='same'),
    
    layers.Flatten(),

    layers.Dense(units=256, activation='relu'),
    layers.Dense(units=10, activation='softmax'),
])

model.summary()



model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])

reduce_lr = ReduceLROnPlateau(monitor='loss', factor=0.3, verbose=1,
                              patience=2, min_lr=0.00000001)

history = model.fit(
    X_train, y_train_encoded, 
    epochs=25,
    validation_split=0.1, 
    callbacks=[reduce_lr],
)

history_frame = pd.DataFrame(history.history)
history_frame.loc[: , ['loss', 'val_loss']].plot()
history_frame.loc[: , ['accuracy', 'val_accuracy']].plot()