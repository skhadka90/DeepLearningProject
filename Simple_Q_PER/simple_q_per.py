#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Feb 26 09:56:10 2017
Modified on Apr 26 2017
author: shengx,rdarbha
"""

#%%
import tensorflow as tf
import numpy as np
import random
import gym
import pickle

DEBUG = True

RENDER = False  # if displaying game graphics real time

LEARNING_RATE = 0.00025 

IMG_X, IMG_Y = 80, 80

action_space = 3  # possible action = 1, 2, 3; still, up, down

EPSILON = 0.01
ALPHA = 0.6

if DEBUG:
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
else:
    max_episode = 21
    max_frame = 10000
    batch_size = 32
    running_reward = None
    future_reward_discount = 0.99
    random_action_prob = 0.9
    rand_prob_step = (0.9 - 0.1)/1000000
    buffer_size = 500000
    frame_skip = 2
    sync_freq = 2000
    update_freq = 4
    save_freq = 200


save_path = "./"

#%% Deep Q-Network Structure
class DQNet():
    def __init__(self,input_size = (80, 80, 1), action_space = 3):

        self.input_x, self.input_y, self.input_frame= input_size
        self.action_space = action_space

    def build_nn(self):
        

        # [batch, in_height, in_width, in_channels]
        # assuming input to be batch_size*84*84*4
        self.input = tf.placeholder(tf.float32, shape=[None, self.input_x, self.input_y, self.input_frame])


        self.W1 = tf.Variable(tf.truncated_normal([6400, 512], stddev = 0.1))
        self.b1 = tf.Variable(tf.truncated_normal([1, 512], stddev = 0.1))
        self.hidden = tf.nn.relu(tf.matmul(tf.reshape(self.input,[-1, 6400]), self.W1) + self.b1)
        self.W2 = tf.Variable(tf.truncated_normal([512, 3], stddev = 0.1))
        self.b2 = tf.Variable(tf.truncated_normal([1, 3], stddev = 0.1))       
        
        self.output = tf.matmul(self.hidden, self.W2) + self.b2

        
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
        return [self.W1, self.b1, self.W2, self.b2]

#%% utility functions

class replayMemory():
    
    def __init__(self, size):
        # [i, :, :, 0:4] is the current state
        # [i, :, :, 1:5] is the next state
        self.frames = np.zeros((size, IMG_X, IMG_Y, 2), dtype = 'float32')
        self.actions = np.zeros((size), dtype = 'int32')
        self.rewards = np.zeros((size), dtype = 'float32')  
        self.done = np.zeros((size), dtype = 'int32')
        self.prob = np.ones((size), dtype = 'float32')
        self.prob = np.divide(self.prob, np.sum(self.prob))
        self.__counter = 0
        self.__size = size
    
    def calc_error(self, sess, Atari_AI_primary, Atari_AI_target):
        #for idx in range(self.__size):
        #    future_rewards[idx] = sess.run(Atari_AI_target.output,
        #                          feed_dict = {Atari_AI_target.input: np.expand_dims(self.frames[idx, :, :, 1], axis = 3)})
        future_rewards = sess.run(Atari_AI_target.output,
                              feed_dict = {Atari_AI_target.input: np.expand_dims(np.expand_dims(self.frames[self.__counter, :, :, 1], axis = 3), axis = 0)})
        targetQ = self.rewards[self.__counter] + future_reward_discount * (1 - self.done[self.__counter]) * np.amax(future_rewards, axis = 1)
        Q = sess.run(Atari_AI_primary.Q,
                          feed_dict = {Atari_AI_primary.actions: np.expand_dims(self.actions[self.__counter], axis = 0), Atari_AI_primary.input: np.expand_dims(np.expand_dims(self.frames[self.__counter, :, :, 0], axis = 3), axis = 0)})
        return np.abs(targetQ - Q);
    
    def add(self, state, action, reward, done, Atari_AI_primary, Atari_AI_target, sess):
        
        self.frames[self.__counter, :, :, : ] = state
        self.actions[self.__counter] = action
        self.rewards[self.__counter] = reward
        self.done[self.__counter] = done
        if sess is not None:
            updated_error = self.rewards[:]
            updated_error[self.__counter] = self.calc_error(sess, Atari_AI_primary, Atari_AI_target)
            self.prob = np.divide((np.abs(updated_error) + EPSILON)**ALPHA, np.sum((np.abs(updated_error) + EPSILON)**ALPHA))
        
        self.__counter += 1
        self.__counter = self.__counter % self.__size
     
    def makeBatch(self, idx):  
        return (self.frames[idx, :, :, 0], self.frames[idx, :, :, 1], self.actions[idx], self.rewards[idx], self.done[idx])

    def makeBatchPrioritized(self,num):
        batch_indices = np.random.choice(a = np.array([idx for idx in range(self.__size)]),size = num,replace = True,p = self.prob)
        return (self.frames[batch_indices, :, :, 0], self.frames[batch_indices, :, :, 1], self.actions[batch_indices], self.rewards[batch_indices], self.done[batch_indices])


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

env = gym.make("Pong-v0")
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
            observation, reward, done, info = env.step(action+1)
            if done:
                break
        
        state = np.roll(state, -1, axis = 2)
        # effective area [34:194, 0:168] with 2*2 downsampling -> 160/2 * 130/2 matrix
        state[:,:,-1] = process_frame(observation) 
        state_input[:,:,0] = state[:,:,-2] - state[:,:,-3]
        state_input[:,:,1] = state[:,:,-1] - state[:,:,-2]
        memory_buffer.add(state_input, action, reward, done, None, None, None)
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

env = gym.make("Pong-v0")


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
while True:
    
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
            observation, reward, done, info = env.step(action+1)
            reward_sum += reward
            if done:
                break
        
        # update the new state and reward and memory buffer
        state = np.roll(state, -1, axis = 2)
        state[:,:,-1] = process_frame(observation) 
        
        state_input[:,:,0] = state[:,:,-2] - state[:,:,-3]
        state_input[:,:,1] = state[:,:,-1] - state[:,:,-2]
        memory_buffer.add(state_input, action, reward, done, Atari_AI_primary, Atari_AI_target, sess)
        
        updates += 1
        if updates % update_freq == 0:
            if random_action_prob > 0.1:    
                random_action_prob -= rand_prob_step
            steps += 1
            
            # randomly sample minibatch from memory
            #batch_sample_index = random.sample(range(buffer_size), batch_size)
            #state_current, state_future, actions, current_rewards, end_game = memory_buffer.makeBatch(batch_sample_index)
            state_current, state_future, actions, current_rewards, end_game = memory_buffer.makeBatchPrioritized(batch_size)
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
                with open('reward_vals.txt','a') as f:
                    f.write('{},{}\n'.format(i_episode, reward_sum))
             
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

env = gym.make("Pong-v0")

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

while True:
    
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
            observation, reward, done, info = env.step(action+1)
            env.render()
            reward_sum += reward
            if done:
                break
        
        # save the model after every 200 updates       
        if done:
            print('\tep {}: reward: {}'.format(i_episode, reward_sum))                
            break        
