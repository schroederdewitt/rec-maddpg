import numpy as np
import torch

from memory import ReplayBuffer


class RandomAgent:
    def __init__(self, index, name, env):
        self.env = env
        self.index = index
        self.name = name
        self.num_actions = self.env.action_space[self.index].n

    def act(self, obs):
        logits = np.random.sample(self.num_actions)
        return logits / np.sum(logits)

    def experience(self, obs, action, reward, new_obs, done):
        pass

    def update(self, agents):
        pass

class MaddpgAgent:
    def __init__(self, index, name, actor, critic, params):
        self.index = index
        self.name = name

        self.actor = actor
        self.critic = critic
        self.actor_target = actor.clone()
        self.critic_target = critic.clone()
        self.actor_optim = torch.optim.Adam(self.actor.parameters(), lr=params.lr_actor)
        self.critic_optim = torch.optim.Adam(self.critic.parameters(), lr=params.lr_critic)
        self.memory = ReplayBuffer(params.memory_size)
        self.mse = torch.nn.MSELoss()

        # params
        self.batch_size = params.batch_size
        self.tau = params.tau
        self.gamma = params.gamma
        self.clip_grads = True
        self.sigma = 0.1

    def update_params(self, target, source):
        zipped = zip(target.parameters(), source.parameters())
        for target_param, source_param in zipped:
            updated_param = target_param.data * (1.0 - self.tau) + \
                source_param.data * self.tau
            target_param.data.copy_(updated_param)

    def act(self, obs):
        obs = torch.tensor(obs, dtype=torch.float, requires_grad=False)
        actions = self.actor(obs).detach()
        noise = self.sigma * torch.randn_like(actions)
        actions = actions + noise
        return actions

    def experience(self, obs, action, reward, new_obs, done):
        self.memory.add(obs, action, reward, new_obs, float(done))

    def train_actor(self, batch):
        ### forward pass ###
        pred_actions = self.actor(batch.observations[self.index])
        actions = list(batch.actions)
        actions[self.index] = pred_actions
        pred_q = self.critic(batch.observations, actions)
        ### backward pass ###
        loss = -pred_q.mean()
        self.actor_optim.zero_grad()
        loss.backward()
        if self.clip_grads:
            torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 0.5)
        self.actor_optim.step()
        return loss

    def train_critic(self, batch, agents):
        """Train critic with TD-target."""
        ### forward pass ###
        # (a_1', ..., a_n') = (mu'_1(o_1'), ..., mu'_n(o_n'))
        next_actions = [a.actor_target(o).detach()
                        for o, a in zip(batch.next_observations, agents)]

        reward = batch.rewards[self.index]
        done = batch.dones[self.index]
        q_next = self.critic_target(batch.next_observations, next_actions)

        # if not done: y = r + gamma * Q(o_1, ..., o_n, a_1', ..., a_n')
        # if done:     y = r
        q_target = reward + (1.0 - done) * self.gamma * q_next

        ### backward pass ###
        # loss(params) = mse(y, Q(o_1, ..., o_n, a_1, ..., a_n))
        loss = self.mse(self.critic(batch.observations, batch.actions), q_target.detach())

        self.critic_optim.zero_grad()
        loss.backward()
        if self.clip_grads:
            torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 0.5)
        self.critic_optim.step()
        return loss

    def update(self, agents):
        # sample minibatch
        memories = [a.memory for a in agents]
        batch = ReplayBuffer.sample_from_memories(memories, self.batch_size)
        
        # train networks
        actor_loss = self.train_actor(batch)
        critic_loss = self.train_critic(batch, agents)

        # update target network params
        self.update_params(self.actor_target, self.actor)
        self.update_params(self.critic_target, self.critic)

        return actor_loss, critic_loss

    def get_state(self):
        return {
            'state_dicts': {
                'actor': self.actor.state_dict(),
                'actor_target': self.actor_target.state_dict(),
                'actor_optim': self.actor_optim.state_dict(),
                'critic': self.critic.state_dict(),
                'critic_target': self.critic_target.state_dict(),
                'critic_optim': self.critic_optim.state_dict()
            },
            'memory': self.memory
        }

    def load_state(self, state):
        for key, value in state['state_dicts'].items():
            getattr(self, key).load_state_dict(value)
        self.memory = state['memory']
