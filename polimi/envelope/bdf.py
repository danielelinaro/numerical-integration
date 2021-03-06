from __future__ import division, print_function, absolute_import
import numpy as np
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import issparse, csc_matrix, eye
from scipy.sparse.linalg import splu
from scipy.optimize._numdiff import group_columns
from scipy.integrate import OdeSolver, DenseOutput, solve_ivp
from scipy.integrate._ivp.bdf import BdfDenseOutput
from .common import (validate_max_step, validate_tol, select_initial_step,
                     norm, EPS, num_jac, validate_first_step,
                     warn_extraneous)

MAX_ORDER = 5
NEWTON_MAXITER = 4
MIN_FACTOR = 0.2
MAX_FACTOR = 10

DEBUG = True
if DEBUG:
    import ipdb

def compute_R(order, factor):
    """Compute the matrix for changing the differences array."""
    I = np.arange(1, order + 1)[:, None]
    J = np.arange(1, order + 1)
    M = np.zeros((order + 1, order + 1))
    M[1:, 1:] = (I - 1 - factor * J) / I
    M[0] = 1
    return np.cumprod(M, axis=0)


def change_D(D, order, factor):
    """Change differences array in-place when step size is changed."""
    R = compute_R(order, factor)
    U = compute_R(order, 1)
    RU = R.dot(U)
    D[:order + 1] = np.dot(RU.T, D[:order + 1])


def solve_bdf_system(fun, t_new, y_predict, c, psi, LU, solve_lu, scale, tol):
    """Solve the algebraic system resulting from BDF method."""
    d = 0
    y = y_predict.copy()
    dy_norm_old = None
    converged = False
    for k in range(NEWTON_MAXITER):
        f = fun(t_new, y)
        if not np.all(np.isfinite(f)):
            break

        dy = solve_lu(LU, c * f - psi - d)
        dy_norm = norm(dy / scale)

        if dy_norm_old is None:
            rate = None
        else:
            rate = dy_norm / dy_norm_old

        # we allow rate to be >= 1, unlike the original solver
        if (rate is not None and rate ** (NEWTON_MAXITER - k) / (1 - rate) * dy_norm > tol):
            break

        y += dy
        d += dy

        if (dy_norm == 0 or
                rate is not None and rate / (1 - rate) * dy_norm < tol):
            converged = True
            break

        dy_norm_old = dy_norm

    return converged, k + 1, y, d


class BDFIntegerSteps(OdeSolver):
    """Implicit method based on backward-differentiation formulas.

    This is a variable order method with the order varying automatically from
    1 to 5. The general framework of the BDF algorithm is described in [1]_.
    This class implements a quasi-constant step size as explained in [2]_.
    The error estimation strategy for the constant-step BDF is derived in [3]_.
    An accuracy enhancement using modified formulas (NDF) [2]_ is also implemented.

    Can be applied in the complex domain.

    Parameters
    ----------
    fun : callable
        Right-hand side of the system. The calling signature is ``fun(t, y)``.
        Here ``t`` is a scalar, and there are two options for the ndarray ``y``:
        It can either have shape (n,); then ``fun`` must return array_like with
        shape (n,). Alternatively it can have shape (n, k); then ``fun``
        must return an array_like with shape (n, k), i.e. each column
        corresponds to a single column in ``y``. The choice between the two
        options is determined by `vectorized` argument (see below). The
        vectorized implementation allows a faster approximation of the Jacobian
        by finite differences (required for this solver).
    t0 : float
        Initial time.
    y0 : array_like, shape (n,)
        Initial state.
    t_bound : float
        Boundary time - the integration won't continue beyond it. It also
        determines the direction of the integration.
    first_step : float or None, optional
        Initial step size. Default is ``None`` which means that the algorithm
        should choose.
    max_step : float, optional
        Maximum allowed step size. Default is np.inf, i.e. the step size is not
        bounded and determined solely by the solver.
    rtol, atol : float and array_like, optional
        Relative and absolute tolerances. The solver keeps the local error
        estimates less than ``atol + rtol * abs(y)``. Here `rtol` controls a
        relative accuracy (number of correct digits). But if a component of `y`
        is approximately below `atol`, the error only needs to fall within
        the same `atol` threshold, and the number of correct digits is not
        guaranteed. If components of y have different scales, it might be
        beneficial to set different `atol` values for different components by
        passing array_like with shape (n,) for `atol`. Default values are
        1e-3 for `rtol` and 1e-6 for `atol`.
    jac : {None, array_like, sparse_matrix, callable}, optional
        Jacobian matrix of the right-hand side of the system with respect to y,
        required by this method. The Jacobian matrix has shape (n, n) and its
        element (i, j) is equal to ``d f_i / d y_j``.
        There are three ways to define the Jacobian:

            * If array_like or sparse_matrix, the Jacobian is assumed to
              be constant.
            * If callable, the Jacobian is assumed to depend on both
              t and y; it will be called as ``jac(t, y)`` as necessary.
              For the 'Radau' and 'BDF' methods, the return value might be a
              sparse matrix.
            * If None (default), the Jacobian will be approximated by
              finite differences.

        It is generally recommended to provide the Jacobian rather than
        relying on a finite-difference approximation.
    jac_sparsity : {None, array_like, sparse matrix}, optional
        Defines a sparsity structure of the Jacobian matrix for a
        finite-difference approximation. Its shape must be (n, n). This argument
        is ignored if `jac` is not `None`. If the Jacobian has only few non-zero
        elements in *each* row, providing the sparsity structure will greatly
        speed up the computations [4]_. A zero entry means that a corresponding
        element in the Jacobian is always zero. If None (default), the Jacobian
        is assumed to be dense.
    vectorized : bool, optional
        Whether `fun` is implemented in a vectorized fashion. Default is False.

    Attributes
    ----------
    n : int
        Number of equations.
    status : string
        Current status of the solver: 'running', 'finished' or 'failed'.
    t_bound : float
        Boundary time.
    direction : float
        Integration direction: +1 or -1.
    t : float
        Current time.
    y : ndarray
        Current state.
    t_old : float
        Previous time. None if no steps were made yet.
    step_size : float
        Size of the last successful step. None if no steps were made yet.
    nfev : int
        Number of evaluations of the right-hand side.
    njev : int
        Number of evaluations of the Jacobian.
    nlu : int
        Number of LU decompositions.

    References
    ----------
    .. [1] G. D. Byrne, A. C. Hindmarsh, "A Polyalgorithm for the Numerical
           Solution of Ordinary Differential Equations", ACM Transactions on
           Mathematical Software, Vol. 1, No. 1, pp. 71-96, March 1975.
    .. [2] L. F. Shampine, M. W. Reichelt, "THE MATLAB ODE SUITE", SIAM J. SCI.
           COMPUTE., Vol. 18, No. 1, pp. 1-22, January 1997.
    .. [3] E. Hairer, G. Wanner, "Solving Ordinary Differential Equations I:
           Nonstiff Problems", Sec. III.2.
    .. [4] A. Curtis, M. J. D. Powell, and J. Reid, "On the estimation of
           sparse Jacobian matrices", Journal of the Institute of Mathematics
           and its Applications, 13, pp. 117-120, 1974.
    """
    def __init__(self, fun, t0, y0, t_bound, max_step=np.inf,
                 rtol=1e-3, atol=1e-6, jac=None, jac_sparsity=None,
                 vectorized=False, first_step=None, **extraneous):
        warn_extraneous(extraneous)
        super(BDFIntegerSteps, self).__init__(fun, t0, y0, t_bound, vectorized,
                                              support_complex=True)
        self.max_step = validate_max_step(max_step)
        self.rtol, self.atol = validate_tol(rtol, atol, self.n)
        f = self.fun(self.t, self.y)
        if first_step is None:
            import ipdb
            ipdb.set_trace()
            #self.h_abs = select_initial_step(self.fun, self.t, self.y, f,
            #                                 self.direction, 1,
            #                                 self.rtol, self.atol)
        else:
            self.min_step = first_step
            #self.min_step = validate_first_step(first_step, t0, t_bound)
        # h_abs can only be an integer multiple of self.min_step
        self.h_abs = self.min_step
        self.h_abs_old = None
        self.error_norm_old = None

        self.newton_tol = max(10 * EPS / rtol, min(0.03, rtol ** 0.5))

        self.jac_factor = None
        self.jac, self.J = self._validate_jac(jac, jac_sparsity)
        if issparse(self.J):
            def lu(A):
                self.nlu += 1
                return splu(A)

            def solve_lu(LU, b):
                return LU.solve(b)

            I = eye(self.n, format='csc', dtype=self.y.dtype)
        else:
            def lu(A):
                self.nlu += 1
                return lu_factor(A, overwrite_a=True)

            def solve_lu(LU, b):
                return lu_solve(LU, b, overwrite_b=True)

            I = np.identity(self.n, dtype=self.y.dtype)

        self.lu = lu
        self.solve_lu = solve_lu
        self.I = I

        kappa = np.array([0, -0.1850, -1/9, -0.0823, -0.0415, 0])
        self.gamma = np.hstack((0, np.cumsum(1 / np.arange(1, MAX_ORDER + 1))))
        self.alpha = (1 - kappa) * self.gamma
        self.error_const = kappa * self.gamma + 1 / np.arange(1, MAX_ORDER + 2)

        D = np.empty((MAX_ORDER + 3, self.n), dtype=self.y.dtype)
        D[0] = self.y
        D[1] = f * self.h_abs * self.direction
        self.D = D

        self.order = 1
        self.n_equal_steps = 0
        self.LU = None

    def _validate_jac(self, jac, sparsity):
        t0 = self.t
        y0 = self.y

        if jac is None:
            if sparsity is not None:
                if issparse(sparsity):
                    sparsity = csc_matrix(sparsity)
                groups = group_columns(sparsity)
                sparsity = (sparsity, groups)

            def jac_wrapped(t, y):
                self.njev += 1
                f = self.fun_single(t, y)
                J, self.jac_factor = num_jac(self.fun_vectorized, t, y, f,
                                             self.atol, self.jac_factor,
                                             sparsity)
                return J
            J = jac_wrapped(t0, y0)
        elif callable(jac):
            J = jac(t0, y0)
            self.njev += 1
            if issparse(J):
                J = csc_matrix(J, dtype=y0.dtype)

                def jac_wrapped(t, y):
                    self.njev += 1
                    return csc_matrix(jac(t, y), dtype=y0.dtype)
            else:
                J = np.asarray(J, dtype=y0.dtype)

                def jac_wrapped(t, y):
                    self.njev += 1
                    return np.asarray(jac(t, y), dtype=y0.dtype)

            if J.shape != (self.n, self.n):
                raise ValueError("`jac` is expected to have shape {}, but "
                                 "actually has {}."
                                 .format((self.n, self.n), J.shape))
        else:
            if issparse(jac):
                J = csc_matrix(jac, dtype=y0.dtype)
            else:
                J = np.asarray(jac, dtype=y0.dtype)

            if J.shape != (self.n, self.n):
                raise ValueError("`jac` is expected to have shape {}, but "
                                 "actually has {}."
                                 .format((self.n, self.n), J.shape))
            jac_wrapped = None

        return jac_wrapped, J

    def _round_step(self, step):
        return np.max((1,np.floor(step/self.min_step))) * self.min_step
    
    def _step_impl(self):
        t = self.t
        D = self.D

        if np.isinf(self.max_step):
            max_step = 1000000 * self.min_step
        else:
            max_step = self._round_step(self.max_step)
        min_step = self.min_step
        if self.h_abs > max_step:
            h_abs = max_step
            change_D(D, self.order, max_step / self.h_abs)
            self.n_equal_steps = 0
        elif self.h_abs < min_step:
            h_abs = min_step
            change_D(D, self.order, min_step / self.h_abs)
            self.n_equal_steps = 0
        else:
            h_abs = self._round_step(self.h_abs)
            change_D(D, self.order, h_abs / self.h_abs)

        if DEBUG:
            print('BDFIntegerSteps._step_impl(%.3f)> y = (%.4f,%.4f) h_abs = %f (%g*%f)' % \
                  (t, self.y[0], self.y[1], h_abs, h_abs/self.min_step, self.min_step))

        atol = self.atol
        rtol = self.rtol
        order = self.order

        alpha = self.alpha
        gamma = self.gamma
        error_const = self.error_const

        J = self.J
        LU = self.LU
        current_jac = self.jac is None

        step_accepted = False
        while not step_accepted:
            if h_abs < min_step:
                return False, self.TOO_SMALL_STEP

            h = h_abs * self.direction
            t_new = t + h

            if self.direction * (t_new - self.t_bound) > 0:
                t_new = t + np.round((self.t_bound - t) / self.min_step) * self.min_step
                if t_new == t:
                    t_new += self.min_step
                change_D(D, order, np.abs(t_new - t) / h_abs)
                self.n_equal_steps = 0
                LU = None

            h = t_new - t
            h_abs = np.abs(h)

            y_predict = np.sum(D[:order + 1], axis=0)

            scale = atol + rtol * np.abs(y_predict)
            psi = np.dot(D[1: order + 1].T, gamma[1: order + 1]) / alpha[order]

            converged = False
            c = h / alpha[order]
            while not converged:
                if LU is None:
                    LU = self.lu(self.I - c * J)

                converged, n_iter, y_new, d = solve_bdf_system(
                    self.fun, t_new, y_predict, c, psi, LU, self.solve_lu,
                    scale, self.newton_tol)

                if not converged:
                    if current_jac:
                        break
                    J = self.jac(t_new, y_predict)
                    LU = None
                    current_jac = True

            if not converged:
                factor = 0.5
                h_abs_prev = h_abs
                h_abs = self._round_step(h_abs * factor)
                if h_abs == h_abs_prev:
                    if DEBUG:
                        print('BDFIntegerSteps._step_impl(%.3f)> cannot reduce the step any further.' % t)
                    return False, self.TOO_SMALL_STEP
                change_D(D, order, h_abs / h_abs_prev)
                self.n_equal_steps = 0
                LU = None
                continue

            safety = 0.9 * (2 * NEWTON_MAXITER + 1) / (2 * NEWTON_MAXITER
                                                       + n_iter)

            scale = atol + rtol * np.abs(y_new)
            error = error_const[order] * d
            error_norm = norm(error / scale)

            if error_norm > 1:
                factor = max(MIN_FACTOR,
                             safety * error_norm ** (-1 / (order + 1)))
                h_abs_prev = h_abs
                h_abs = self._round_step(h_abs * factor)
                if h_abs == h_abs_prev:
                    if DEBUG:
                        print('BDFIntegerSteps._step_impl(%.3f)> cannot reduce the step any further.' % t)
                    return False, self.TOO_SMALL_STEP
                change_D(D, order, h_abs / h_abs_prev)
                self.n_equal_steps = 0
                # As we didn't have problems with convergence, we don't
                # reset LU here.
            else:
                step_accepted = True

        self.n_equal_steps += 1

        self.t = t_new
        self.y = y_new

        self.h_abs = h_abs
        self.J = J
        self.LU = LU

        # Update differences. The principal relation here is
        # D^{j + 1} y_n = D^{j} y_n - D^{j} y_{n - 1}. Keep in mind that D
        # contained difference for previous interpolating polynomial and
        # d = D^{k + 1} y_n. Thus this elegant code follows.
        D[order + 2] = d - D[order + 1]
        D[order + 1] = d
        for i in reversed(range(order + 1)):
            D[i] += D[i + 1]

        if self.n_equal_steps < order + 1:
            return True, None

        if order > 1:
            error_m = error_const[order - 1] * D[order]
            error_m_norm = norm(error_m / scale)
        else:
            error_m_norm = np.inf

        if order < MAX_ORDER:
            error_p = error_const[order + 1] * D[order + 2]
            error_p_norm = norm(error_p / scale)
        else:
            error_p_norm = np.inf

        error_norms = np.array([error_m_norm, error_norm, error_p_norm])
        factors = error_norms ** (-1 / np.arange(order, order + 3))

        delta_order = np.argmax(factors) - 1
        if DEBUG:
            if delta_order > 0:
                print('BDFIntegerSteps._step_impl(%.3f)> increasing order (%d -> %d).' % (t,order,order+delta_order))
            elif delta_order < 0:
                print('BDFIntegerSteps._step_impl(%.3f)> decreasing order (%d -> %d).' % (t,order,order+delta_order))
            else:
                print('BDFIntegerSteps._step_impl(%.3f)> leaving order unchanged (%d).' % (t,order))
        order += delta_order
        self.order = order

        factor = min(MAX_FACTOR, safety * np.max(factors))
        h_abs_prev = self.h_abs
        self.h_abs = self._round_step(factor * self.h_abs)
        if self.h_abs == h_abs_prev:
            if DEBUG:
                print('BDFIntegerSteps._step_impl(%.3f)> cannot at least double the step.' % t)
            return False, self.TOO_SMALL_STEP
        change_D(D, order, self.h_abs / h_abs_prev)
        self.n_equal_steps = 0
        self.LU = None

        return True, None

    def _dense_output_impl(self):
        raise NotImplementedError
        #return BdfDenseOutput(self.t_old, self.t, self.h_abs * self.direction,
        #                      self.order, self.D[:self.order + 1].copy())


class BDFEnvelope(OdeSolver):
    def __init__(self, fun, t0, y0, t_bound, T_guess, max_step=np.inf,
                 rtol=1e-3, atol=1e-6, fun_rtol=1e-6, fun_atol=1e-8, dTtol=1e-2,
                 jac=None, jac_sparsity=None, vectorized=False, fun_method='RK45',
                 **extraneous):
        warn_extraneous(extraneous)
        super(BDFEnvelope, self).__init__(lambda t,y: self._envelope_fun(t,y,None),
                                     t0, y0, t_bound, vectorized=False,
                                     support_complex=False)
        self.dTtol = dTtol
        self.max_step = max_step
        self.rtol, self.atol = validate_tol(rtol, atol, self.n)
        self.original_fun_rtol, self.original_fun_atol = validate_tol(fun_rtol, fun_atol, self.n)
        self.original_fun = fun
        self.original_jac = jac
        self.original_jac_sparsity = jac_sparsity
        self.original_fun_vectorized = vectorized
        self.original_fun_method = fun_method
        self._envelope_fun(t0,y0,T_guess)
        self.T = self.T_new
        if DEBUG:
            print('BDFEnvelope.__init__> the period is estimated at %.10f sec.' % self.T)
        #self.solver = BDFIntegerSteps(self.fun, t0, y0, t_bound, max_step,
        #                              rtol, atol, jac=None, jac_sparsity=None,
        #                              vectorized=False, first_step=self.T)
        self.SINGLE_STEP = 1
        self.INTEGER_STEPS = 2
        self.mode = self.SINGLE_STEP
        self.n_good_steps = 0

    def _step_impl(self):
        if self.mode == self.SINGLE_STEP:
            self.fun(self.t,self.y)
            dT = np.abs(self.T - self.T_new)
            if DEBUG:
                print('BDFEnvelope._step_impl(%.3f)> dT = %e' % (self.t,dT))
            self.t_old = self.t
            self.t = self.t_new
            self.y = self.y_new
            self.T_old = self.T
            self.T = self.T_new
            self.nfev += 1
            if dT < self.dTtol:
                self.n_good_steps += 1
            else:
                self.n_good_steps = 0
            if self.n_good_steps > 3:
                self.mode = self.INTEGER_STEPS
                if DEBUG:
                    print('BDFEnvelope._step_impl(%.3f)> switching integration mode to INTEGER_STEPS.' % self.t)
                self.solver = BDFIntegerSteps(self.fun, self.t, self.y, self.t_bound,
                                              self.max_step, self.rtol, self.atol,
                                              jac=None, jac_sparsity=None,
                                              vectorized=False, first_step=self.T)


            return True,None

        success,message = self.solver._step_impl()
        dT = np.abs(self.T - self.T_new)
        if DEBUG:
            print('BDFEnvelope._step_impl(%.3f)> dT = %e' % (self.t,dT))
        if success and dT < self.dTtol:
            self.T = self.T_new
            self.solver.min_step = self.T
            self.status = self.solver.status
            self.t_old = self.solver.t_old
            self.t = self.solver.t
            self.y = self.solver.y
            self.dense_output = self.solver.dense_output
            self.direction = self.solver.direction
            self.nfev = self.solver.nfev
            self.njev = self.solver.njev
            self.nlu = self.solver.nlu
            return success,message

        self.fun(self.t,self.y)
        self.t_old = self.t
        self.t = self.t_new
        self.y = self.y_new
        self.T = self.T_new
        self.nfev += 1
        self.solver = BDFIntegerSteps(self.fun, self.t, self.y, self.t_bound,
                                      self.max_step, self.rtol, self.atol,
                                      jac=None, jac_sparsity=None,
                                      vectorized=False, first_step=self.T)
        return True,None
        
    def _envelope_fun(self,t,y,T_guess=None):
        if T_guess is None:
            T_guess = self.T
        # find the equation of the plane containing y and
        # orthogonal to fun(t,y)
        f = self.original_fun(t,y)
        w = f/np.linalg.norm(f)
        b = -np.dot(w,y)
        # first integration without events, because event(t0) = 0
        # and the solver goes crazy
        if self.original_fun_method == 'BDF':
            sol_a = solve_ivp(self.original_fun,[t,t+0.75*T_guess],y,
                              self.original_fun_method,jac=self.original_jac,
                              jac_sparsity=self.original_jac_sparsity,
                              vectorized=self.original_fun_vectorized,
                              dense_output=True,rtol=self.original_fun_rtol,
                              atol=self.original_fun_atol)
            sol_b = solve_ivp(self.original_fun,[sol_a['t'][-1],t+1.5*T_guess],
                              sol_a['y'][:,-1],self.original_fun_method,jac=self.original_jac,
                              jac_sparsity=self.original_jac_sparsity,
                              vectorized=self.original_fun_vectorized,
                              events=lambda t,y: np.dot(w,y)+b,dense_output=True,
                              rtol=self.original_fun_rtol,atol=self.original_fun_atol)
        else:
            sol_a = solve_ivp(self.original_fun,[t,t+0.75*T_guess],y,
                              self.original_fun_method,vectorized=self.original_fun_vectorized,
                              dense_output=True,rtol=self.original_fun_rtol,
                              atol=self.original_fun_atol)
            sol_b = solve_ivp(self.original_fun,[sol_a['t'][-1],t+1.5*T_guess],
                              sol_a['y'][:,-1],self.original_fun_method,
                              vectorized=self.original_fun_vectorized,
                              events=lambda t,y: np.dot(w,y)+b,dense_output=True,
                              rtol=self.original_fun_rtol,atol=self.original_fun_atol)

        for t_ev in sol_b['t_events'][0]:
            x_ev = sol_b['sol'](t_ev)
            f = self.original_fun(t_ev,x_ev)
            # check whether the crossing of the plane is in
            # the same direction as the initial point
            if np.dot(w,f/np.linalg.norm(f))+b > 0:
                T = t_ev-t
                break
        try:
            self.T_new = T
        except:
            self.T_new = T_guess
            if DEBUG:
                print('BDFEnvelope._envelope_fun(%.3f)> T = T_guess = %.6f.' % (t,self.T_new))
        self.t_new = t + self.T_new
        self.y_new = sol_b['sol'](self.t_new)
        if DEBUG:
            print('BDFEnvelope._envelope_fun(%.3f)> y = (%.4f,%.4f) T = %.6f.' % (t,self.y_new[0],self.y_new[1],self.T_new))
        # return the "vector field" of the envelope
        return 1./self.T_new * (self.y_new - sol_a['sol'](t))

    def _dense_output_impl(self):
        raise NotImplementedError
        #return BdfDenseOutput(self.t_old, self.t, self.h_abs * self.direction,
        #                      self.order, self.D[:self.order + 1].copy())


#class BdfDenseOutput(DenseOutput):
#    def __init__(self, t_old, t, h, order, D):
#        super(BdfDenseOutput, self).__init__(t_old, t)
#        self.order = order
#        self.t_shift = self.t - h * np.arange(self.order)
#        self.denom = h * (1 + np.arange(self.order))
#        self.D = D
#
#    def _call_impl(self, t):
#        if t.ndim == 0:
#            x = (t - self.t_shift) / self.denom
#            p = np.cumprod(x)
#        else:
#            x = (t - self.t_shift[:, None]) / self.denom[:, None]
#            p = np.cumprod(x, axis=0)
#
#        y = np.dot(self.D[1:].T, p)
#        if y.ndim == 1:
#            y += self.D[0]
#        else:
#            y += self.D[0, :, None]
#
#        return y

