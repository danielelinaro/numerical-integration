
import numpy as np
from scipy.integrate import solve_ivp, OdeSolution
from scipy.integrate._ivp.ivp import OdeResult

__all__ = ['DynamicalSystem', 'SwitchingSystem', 'VanderPol', 'Boost', 'solve_ivp_switch']


class DynamicalSystem (object):

    def __init__(self, n_dim, with_variational=False, variational_T=1):
        self.n_dim = n_dim
        self.with_variational = with_variational
        self.variational_T = variational_T


    def __call__(self, t, y):
        T = self.variational_T

        if not self.with_variational:
            return T * self._fun(t*T,y)

        N = self.n_dim
        phi = np.reshape(y[N:N+N**2], (N,N))
        J = self._J(t * T, y[:N])
        return np.concatenate((T * self._fun(t*T, y[:N]), \
                               T * (J @ phi).flatten()))


    def jac(self, t, y):
        T = self.variational_T
        return T * self._J(t*T, y)


    def _fun(self, t, y):
        raise NotImplementedError


    def _J(self, t, y):
        raise NotImplementedError


    @property
    def with_variational(self):
        return self._with_variational


    @with_variational.setter
    def with_variational(self, value):
        if not isinstance(value, bool):
            raise ValueError('value must be of boolean type')
        self._with_variational = value


    @property
    def variational_T(self):
        return self._variational_T


    @variational_T.setter
    def variational_T(self, T):
        if T <= 0:
            raise ValueError('T must be greater than 0')
        self._variational_T = T


class SwitchingSystem (DynamicalSystem):

    def __init__(self, n_dim, vector_field_index, with_variational=False, variational_T=1):
        super(SwitchingSystem, self).__init__(n_dim, with_variational, variational_T)
        self.n_dim = n_dim
        self.vector_field_index = vector_field_index
        self.event_functions = []
        self.event_derivatives = []
        self.event_gradients = []


    def handle_event(self, event_index, t, y):
        if self.with_variational:
            f_before = np.array(self._fun(t,y[:self.n_dim]), ndmin=2).transpose()

        self._handle_event(event_index, t, y)

        if self.with_variational:
            f_after = np.array(self._fun(t,y[:self.n_dim]), ndmin=2).transpose()
            df = f_after - f_before
            dh = self.event_derivatives[event_index](t,y)
            eta_T = self.event_gradients[event_index](t,y).transpose()
            S = np.eye(self.n_dim) + ((df / ((eta_T @ f_before) + dh)) @ eta_T)
        else:
            S = None

        return S


    def _handle_event(self, event_index, t, y):
        raise NotImplementedError


    def _check_vector_field_index(self, index):
        raise NotImplementedError


    @property
    def vector_field_index(self):
        return self._vector_field_index


    @vector_field_index.setter
    def vector_field_index(self, index):
        if not self._check_vector_field_index(index):
            raise ValueError('Wrong value of vector field index')
        self._vector_field_index = index


    @property
    def event_functions(self):
        return self._event_functions


    @event_functions.setter
    def event_functions(self, events):
        self._event_functions = events


    @property
    def event_derivatives(self):
        return self._event_derivatives


    @event_derivatives.setter
    def event_derivatives(self, derivatives):
        self._event_derivatives = derivatives


    @property
    def event_gradients(self):
        return self._event_gradients


    @event_gradients.setter
    def event_gradients(self, gradients):
        self._event_gradients = gradients


class VanderPol (DynamicalSystem):

    def __init__(self, epsilon, A, T, with_variational=False, variational_T=1):
        super(VanderPol, self).__init__(2, with_variational, variational_T)

        self.epsilon = epsilon

        if np.isscalar(A):
            self.A = np.array([A])
        elif isinstance(A, list) or isinstance(A, tuple):
            self.A = np.array(A)
        else:
            self.A = A

        if np.isscalar(T):
            self.T = np.array([T])
        elif isinstance(T, list) or isinstance(T, tuple):
            self.T = np.array(T)
        else:
            self.T = T

        self.F = np.array([1./t for t in T])
        self.n_forcing = len(self.F)


    def _fun(self, t, y):
        ydot = np.array([
            y[1],
            self.epsilon*(1-y[0]**2)*y[1] - y[0]
        ])
        for i in range(self.n_forcing):
            ydot[1] += self.A[i] * np.cos(2 * np.pi * self.F[i] * t)
        return ydot


    def _J(self, t, y):
        return np.array([
            [0, 1],
            [-2 * self.epsilon * y[0] * y[1] - 1, self.epsilon * (1 - y[0] ** 2)]
        ])


class Boost (SwitchingSystem):

    def __init__(self, vector_field_index,
                 T=20e-6, ki=1.5, Vref=5, Vin=5, R=5,
                 L=10e-6, C=47e-6, Rs=0, clock_phase=0,
                 with_variational=False, variational_T=1):

        if not with_variational:
            if not variational_T is None and variational_T != 1:
                print('with_variational is False, ignoring value of variational_T')
            variational_T = 1

        super(Boost, self).__init__(2, vector_field_index, with_variational, variational_T)

        self.T = T
        self.F = 1./T
        self.phi = clock_phase
        self.ki = ki
        self.Vref = Vref
        self.Vin = Vin
        self.R = R
        self.L = L
        self.C = C
        self.Rs = Rs

        self._make_matrixes()

        self.event_functions = [lambda t,y: Boost.manifold(self, t, y), \
                                lambda t,y: Boost.clock(self, t*self.variational_T, y)]
        for event_fun in self._event_functions:
            event_fun.direction = 1
            event_fun.terminal = 1

        self.event_derivatives = [lambda t,y: Boost.manifold_der(self, t*self.variational_T, y),
                                  lambda t,y: Boost.clock_der(self, t*self.variational_T, y)]

        self.event_gradients = [lambda t,y: Boost.manifold_grad(self, t*self.variational_T, y),
                                lambda t,y: Boost.clock_grad(self, t*self.variational_T, y)]


    def _fun(self, t, y):
        return (self.A[self.vector_field_index] @ y) + self.B


    def _J(self, t, y):
        return self.A[self.vector_field_index]


    def _handle_event(self, event_index, t, y):
        self.vector_field_index = 1 - event_index


    def clock(self, t, y):
        return np.sin(2*np.pi*self.F*t-self.phi)


    def clock_der(self, t, y):
        return 2 * np.pi * self.F * np.cos(2*np.pi*self.F*t-self.phi)


    def clock_grad(self, t, y):
        return np.array([0, 0], ndmin=2).transpose()


    def manifold(self, t, y):
        return self.ki * y[1] - self.Vref


    def manifold_der(self, t, y):
        return 0


    def manifold_grad(self, t, y):
        return np.array([0,self.ki], ndmin=2).transpose()


    def _check_vector_field_index(self, index):
        if index in (0,1):
            return True
        return False


    def _make_matrixes(self):
        self.A = [np.array([ [-1/(self.R*self.C), 0],   [0, -self.Rs/self.L]    ]), \
                  np.array([ [-1/(self.R*self.C), 1/self.C], [-1/self.L, -self.Rs/self.L] ])]
        self.B  = np.array([0, self.Vin/self.L])



def solve_ivp_switch(sys, t_span, y0, **kwargs):

    kwargs_copy = kwargs.copy()

    t_cur = t_span[0]
    t_end = t_span[1]
    y_cur = y0

    t = np.array([])
    y = np.array([[] for _ in range(y0.shape[0])])

    n_system_events = len(sys.event_functions)

    # the event functions of the original system
    event_functions = sys.event_functions.copy()

    # user event function passed as arguments
    user_event_idx = []
    try:
        user_events = kwargs_copy.pop('events')
        if not isinstance(user_events, list):
            n_user_events = 1
            user_event_idx.append(len(event_functions))
            event_functions.append(user_events)
        else:
            n_user_events = len(user_events)
            user_event_idx = []
            for event in user_events:
                user_event_idx.append(len(event_functions))
                event_functions.append(event)
        t_events = [[] for _ in range(n_user_events)]
        y_events = [[] for _ in range(n_user_events)]
    except:
        n_user_events = 0
        t_events = None
        y_events = None

    # one last event to stop at the exact time instant
    event_functions.append(lambda t,y: t - t_end)
    event_functions[-1].terminal = 0
    event_functions[-1].direction = 1

    n_events = n_system_events + n_user_events + 1

    try:
        dense_output = kwargs_copy.pop('dense_output')
    except:
        dense_output = False

    if dense_output:
        ts = np.array([])
        interpolants = []

    terminate = False
    nfev = 0
    njev = 0
    nlu = 0
    while np.abs(t_cur - t_end) > 1e-10 and not terminate:
        sol = solve_ivp(sys, [t_cur,t_end*1.001], y_cur,
                        events=event_functions,
                        dense_output=True, **kwargs_copy)
        nfev += sol['nfev']
        njev += sol['njev']
        nlu += sol['nlu']
        if not sol['success']:
            break
        t_next = np.inf
        ev_idx = None
        for i,t_ev in enumerate(sol['t_events']):
            if len(t_ev) > 0 and t_ev[-1] != t_cur and np.abs(t_ev[-1] - t_next) > 1e-10:
                t_next = t_ev[-1]
                ev_idx = i
        if ev_idx is None:
            t_next = sol['t'][-1]
            y_next = sol['y'][:,-1]
        elif ev_idx in user_event_idx:
            y_next = sol['sol'](t_next)
            t_events[ev_idx - n_system_events].append(t_next)
            y_events[ev_idx - n_system_events].append(sol['sol'](t_next))
            if event_functions[ev_idx].terminal:
                terminate = True
        else:
            y_next = sol['sol'](t_next)
            if ev_idx < n_events-1:
                S = sys.handle_event(ev_idx, t_next, y_next)
                if sys.with_variational:
                    N = sys.n_dim
                    phi = S @ np.reshape(y_next[N:], (N,N))
                    y_next[N:] = phi.flatten()
        idx, = np.where(sol['t'] < t_next)
        t = np.append(t, sol['t'][idx])
        t = np.append(t, t_next)
        y = np.append(y, sol['y'][:,idx], axis=1)
        y = np.append(y, np.array([y_next]).transpose(), axis=1)
        if dense_output:
            if len(ts) > 0 and ts[-1] == sol['sol'].ts[0]:
                ts = np.concatenate((ts, sol['sol'].ts[1:]))
            else:
                ts = np.concatenate((ts, sol['sol'].ts))
            interpolants += sol['sol'].interpolants
        t_cur = t_next
        y_cur = y_next

    if dense_output:
        ode_sol = OdeSolution(ts, interpolants)
    else:
        ode_sol = None

    return OdeResult(t=t, y=y, sol=ode_sol, t_events=t_events, y_events=y_events, \
                     nfev=nfev, njev=njev, nlu=nlu, status=sol['status'], \
                     message=sol['message'], success=sol['success'])
