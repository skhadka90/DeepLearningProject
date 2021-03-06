#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Feb 26 09:56:10 2017
@author: shengx, gaconte

Trains a neural network to play Q*bert.
The network is composed of 2 hidden layers.

"""

#%%
import tensorflow as tf
import numpy as np
import random
import gym
import pickle

DEBUG = True

RENDER = False  # if displaying game graphics real time

IMG_X, IMG_Y = 80, 80

ACTION_SPACE = 6  # possible action = 1, 2, 3; still, up, down
TRAIN_EPISODES = 21000
TEST_EPISODES = 100


LEARNING_RATE = 0.001
max_episode = 21
max_frame = 10000
batch_size = 32
running_reward = None
future_reward_discount = 0.99
random_action_prob = 0.9
rand_prob_step = (0.9 - 0.1)/60000
buffer_size = 60000
frame_skip = 2
sync_freq = 2000
update_freq = 4
save_freq = 100

save_path = "./qbert2h/"

#%% Deep Q-Network Structure
class DQNet():
    def __init__(self,input_size = (80, 80, 1), action_space = ACTION_SPACE):

        self.input_x, self.input_y, self.input_frame= input_size
        self.action_space = action_space

    def build_nn(self):
        

        # [batch, in_height, in_width, in_channels]
        # assuming input to be batch_size*84*84*4
        self.input = tf.placeholder(tf.float32, shape=[None, self.input_x, self.input_y, self.input_frame])


        self.W1 = tf.Variable(tf.truncated_normal([6400, 512], stddev = 0.1))
        self.b1 = tf.Variable(tf.truncated_normal([1, 512], stddev = 0.1))
        self.hidden1 = tf.nn.relu(tf.matmul(tf.reshape(self.input,[-1, 6400]), self.W1) + self.b1)
        self.W2 = tf.Variable(tf.truncated_normal([512, 256], stddev = 0.1))
        self.b2 = tf.Variable(tf.truncated_normal([1, 256], stddev = 0.1))
        self.hidden2 = tf.nn.relu(tf.matmul(tf.reshape(self.hidden1,[-1, 512]), self.W2) + self.b2)     
        self.W3 = tf.Variable(tf.truncated_normal([256, ACTION_SPACE], stddev = 0.1))
        self.b3 = tf.Variable(tf.truncated_normal([1, ACTION_SPACE], stddev = 0.1))
        self.output = tf.matmul(self.hidden2, self.W3) + self.b3

        
        ###########################################################
        # prediction, loss, and update
        
        self.predict = tf.argmax(self.output, 1)
        
        self.targetQ = tf.placeholder(shape=[None],dtype=tf.float32)
        
        self.actions = tf.placeholder(shape=[None],dtype=tf.int32)
        
        self.actions_onehot = tf.one_hot(self.actions, self.action_space, dtype=tf.float32)
        
        self.Q = tf.reduce_sum((self.output * self.actions_onehot), 
                               reduction_indices=1)
        
        self.loss = tf.reduce_mean(tf.square(self.targetQ - self.Q))

        self.update = tf.train.AdamOptimizer(learning_rate = LEARNING_RATE).minimize(self.loss)

    def variable_list(self):
        return [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

#%% utility functions

class replayMemory():
    
    def __init__(self, size):
        # [i, :, :, 0:4] is the current state
        # [i, :, :, 1:5] is the next state
        self.frames = np.zeros((size, IMG_X, IMG_Y, 2), dtype = 'float32')
        self.actions = np.zeros((size), dtype = 'int32')
        self.rewards = np.zeros((size), dtype = 'float32')  
        self.done = np.zeros((size), dtype = 'int32')
        self.__counter = 0
        self.__size = size
        
    def add(self, state, action, reward, done):
        
        self.frames[self.__counter, :, :, : ] = state
        self.actions[self.__counter] = action
        self.rewards[self.__counter] = reward
        self.done[self.__counter] = done
        
        self.__counter += 1
        self.__counter = self.__counter % self.__size
     
    def makeBatch(self, idx):  
        return (self.frames[idx, :, :, 0], self.frames[idx, :, :, 1], self.actions[idx], self.rewards[idx], self.done[idx])


def process_frame(frame):
    # input a single frame
    # crop & downsample & average over 3 color channels 
    return np.mean(frame[34: 194 : 2, 0: 160 : 2, :], axis = 2, dtype = 'float32') > 100
 
def copy_variables(from_nn, to_nn, sess):   
    for i in range(len(from_nn)):
        op = to_nn[i].assign(from_nn[i].value())
        sess.run(op)


#%%
###################################################################
# pre-training, fill the replay memory buffer with 10,000 random examples
memory_buffer = replayMemory(buffer_size)
buffer_counter = 0
state_input = np.zeros((IMG_X, IMG_Y, 2), dtype = 'float32')

env = gym.make("Qbert-v0")
while True:
    
    # reset the game environment, take a initial screen shot
    observation = env.reset()
    # the state of current game play, 0:2 is 3 previous frame,
    # 3 is the current frame, 4 is the frame after action
    state = np.zeros((IMG_X, IMG_Y, 5), dtype = 'float32')
    state[:,:,-1] = process_frame(observation)
      
    for t in range(buffer_size):

        action = random.randint(0, 2)
        
        # run the game with same action for a few frames
        for _ in range(frame_skip):
            observation, reward, done, info = env.step(action)
            if done:
                break
        
        state = np.roll(state, -1, axis = 2)
        # effective area [34:194, 0:168] with 2*2 downsampling -> 160/2 * 130/2 matrix
        state[:,:,-1] = process_frame(observation) 
        state_input[:,:,0] = state[:,:,-2] - state[:,:,-3]
        state_input[:,:,1] = state[:,:,-1] - state[:,:,-2]
        memory_buffer.add(state_input, action, reward, done)
        buffer_counter += 1
                
        if done:
            print("Episode finished after {} timesteps".format(t+1))
            break
    
    if buffer_counter > buffer_size:
        break
env.close()
  
#%%
###################################################################
# Initialize environment

env = gym.make("Qbert-v0")


tf.reset_default_graph()
Atari_AI_primary = DQNet()
Atari_AI_primary.build_nn()

Atari_AI_target = DQNet()
Atari_AI_target.build_nn()

init_op = tf.global_variables_initializer()
reward_log = []

sess = tf.Session()
sess.run(init_op)

# Initialize saver
saver = tf.train.Saver()

try:
    ckpt = tf.train.get_checkpoint_state(save_path)
    load_path = ckpt.model_checkpoint_path
    saver.restore(sess, load_path)
    f = open(save_path + 'reward_log.cptk','rb')
    reward_log = pickle.load(f)
    f.close()
    
    random_action_prob = 0.1
    
    print("Session restored...")
except:
    primary_variables = Atari_AI_primary.variable_list()
    target_variables = Atari_AI_target.variable_list()
    copy_variables(primary_variables, target_variables, sess)
    print("Nothing to restore...")


# start training
i_episode = 0
updates = 0
steps = 0
while i_episode < TRAIN_EPISODES:
    
    i_episode += 1
    
    observation = env.reset()
    
    state = np.zeros((IMG_X, IMG_Y, 5), dtype = 'float32')
    state[:,:,-1] = process_frame(observation)
    reward_sum = 0
    
    for t in range(max_frame):
        if RENDER:
            env.render()
        # select an action based on the action-value function Q
        if np.random.random_sample() > random_action_prob:
            # use model to predict action
            #state_input[:,:,0] = state[:,:,-2] - state[:,:,-3]
            action = sess.run(Atari_AI_primary.predict,
                              feed_dict = {Atari_AI_primary.input: np.reshape(state[:,:,-1] - state[:,:,-2], [1, 80, 80, 1])})[0]
        else: 
            # random action
            action = random.randint(0, 2) # random sample action from 1 to 3
            
        # excute the action for a few steps
        for _ in range(frame_skip):
            observation, reward, done, info = env.step(action)
            reward_sum += reward
            if done:
                break
        
        # update the new state and reward and memory buffer
        state = np.roll(state, -1, axis = 2)
        state[:,:,-1] = process_frame(observation) 
        
        state_input[:,:,0] = state[:,:,-2] - state[:,:,-3]
        state_input[:,:,1] = state[:,:,-1] - state[:,:,-2]
        memory_buffer.add(state_input, action, reward, done)
        
        updates += 1
        if updates % update_freq == 0:
            if random_action_prob > 0.1:    
                random_action_prob -= rand_prob_step
            steps += 1
            
            # randomly sample minibatch from memory
            batch_sample_index = random.sample(range(buffer_size), batch_size)
            state_current, state_future, actions, current_rewards, end_game = memory_buffer.makeBatch(batch_sample_index)
            future_rewards = sess.run(Atari_AI_target.output,
                                  feed_dict = {Atari_AI_target.input: np.expand_dims(state_future, axis = 3)})
            targetQ = current_rewards + future_reward_discount * (1 - end_game) * np.amax(future_rewards, axis = 1)
        
            # update the target-value function Q
            
            sess.run(Atari_AI_primary.update, feed_dict = {
                Atari_AI_primary.input: np.expand_dims(state_current, axis = 3),
                Atari_AI_primary.actions: actions,
                Atari_AI_primary.targetQ: targetQ})
        
            # every C step reset Q' = Q
            if steps % sync_freq == 0:
                primary_variables = Atari_AI_primary.variable_list()
                target_variables = Atari_AI_target.variable_list()
                copy_variables(primary_variables, target_variables, sess)
        
        # save the model after every 200 updates       
        if done:
            running_reward = reward_sum if running_reward is None else running_reward * 0.99 + reward_sum * 0.01

            if DEBUG:
                if i_episode % 10 == 0:
                    print('ep {}: updates {}: reward: {}, mean reward: {:3f}'.format(i_episode, updates, reward_sum, running_reward))
                else:
                    print('\tep {}: reward: {}'.format(i_episode, reward_sum))
             
            # saving results    
            if i_episode % 10 == 0:
                reward_log.append(running_reward)
                
            if i_episode % save_freq == 0:
                saver.save(sess, save_path+'model-'+str(i_episode)+'.cptk')
                f = open(save_path + 'reward_log.cptk','wb')
                pickle.dump(reward_log, f)
                f.close()
                
            break
        
        
#%% testing 
###################################################################
# Initialize environment

env = gym.make("Qbert-v0")

tf.reset_default_graph()
Atari_AI_primary = DQNet()
Atari_AI_primary.build_nn()

Atari_AI_target = DQNet()
Atari_AI_target.build_nn()

init_op = tf.global_variables_initializer()

sess = tf.Session()
sess.run(init_op)

# Initialize saver
saver = tf.train.Saver()

try:
    ckpt = tf.train.get_checkpoint_state(save_path)
    load_path = ckpt.model_checkpoint_path
    saver.restore(sess, load_path)
    f = open(save_path + 'reward_log.cptk','rb')
    reward_log = pickle.load(f)
    f.close()
    
    
    print("Session restored...")
except:
    primary_variables = Atari_AI_primary.variable_list()
    target_variables = Atari_AI_target.variable_list()
    copy_variables(primary_variables, target_variables, sess)
    print("Nothing to restore...")


# start training
i_episode = 0
total_reward_sum = 0
while i_episode < TEST_EPISODES:
    
    i_episode += 1
    
    observation = env.reset()
    
    state = np.zeros((IMG_X, IMG_Y, 5), dtype = 'float32')
    state[:,:,-1] = process_frame(observation)
    reward_sum = 0
    
    for t in range(max_frame):

        # select an action based on the action-value function Q
        action = sess.run(Atari_AI_primary.predict,
                              feed_dict = {Atari_AI_primary.input: np.reshape(state[:,:,-1] - state[:,:,-2], [1, 80, 80, 1])})[0]
        # excute the action for a few steps
        for _ in range(frame_skip):
            observation, reward, done, info = env.step(action)
            #env.render()
            reward_sum += reward
            if done:
                break
        
        # save the model after every 200 updates       
        if done:
            total_reward_sum += reward_sum
            print('\tep {}: reward: {} total_reward: {} action: {}'.format(i_episode, reward_sum, total_reward_sum, action))   
            break
average_reward = total_reward_sum/TEST_EPISODES
print('\taverage_reward: ' + str(average_reward))
