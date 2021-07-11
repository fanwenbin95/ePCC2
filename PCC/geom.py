import os.path
import numpy as np
import logging
from .util import const2para, find_mol_graph
from .const import covr
from .const import val as val_default

class geomParser():

    def __init__(self, path=None):
        self.path = path
        self.format = ''
        self.q = 0 #
        return

    def __check_exist(self):
        if os.path.exists(self.path):
            return True
        else:
            raise FileNotFoundError(self.path)

    def __choose_format(self):
        file_name = os.path.basename(self.path)
        par = file_name.split('.')
        npar = len(par)
        ext = par[-1]

        if npar == 1:
            if 'CAR' in file_name:
                self.format = 'VASP'
                self.__read_vasp()
            else:
                raise IOError('File type not support! ')
        elif npar == 2:
            raise IOError('File type not support! ')
        else:
            raise IOError('File type not support! ')

        return

    def __read_vasp(self):
        assert self.format == 'VASP'

        f = open(self.path, 'r').readlines()

        factor = float(f[1])
        lattice_const = np.zeros([3,3])

        lattice_const[:, 0] = [float(x) for x in f[2].split()]
        lattice_const[:, 1] = [float(x) for x in f[3].split()]
        lattice_const[:, 2] = [float(x) for x in f[4].split()]

        lattice_const *= factor

        # read element list
        ele_name = f[5].split()
        ele_num = [int(x) for x in f[6].split()]
        assert len(ele_num) == len(ele_name)
        Nele = len(ele_name)

        ele_list = []
        for ele in range(Nele):
            for i in range(ele_num[ele]):
                ele_list.append(ele_name[ele].strip())
        assert len(ele_list) == np.sum(ele_num)
        Natom = len(ele_list)

        q = np.zeros([3, Natom])
        for atom in range(Natom):
            q[:, atom] = [float(x) for x in f[8+atom].split()[:3]]

        # convert to Cartesian coordinate
        if f[7].strip()[0].lower() == 'd':
            q = np.dot(lattice_const, q)

        self.igeom(Natom, ele_list, q, lattice_const)

        return

    def __read_val(self):

        val_file = 'val.txt'
        val = np.zeros(self.Natom)
        if os.path.exists(val_file):
            f = open('val.txt', 'r')
            l = f.readlines()
            assert len(l) == self.Natom
            for i in range(self.Natom):
                val[i] = float(l[i].strip().split()[-1])
        else:
            for i in range(self.Natom):
                val[i] = val_default[self.ele_list[i]]
        self.val = val

        return

    def igeom(self, Natom, ele_list, q, lattice_const):

        self.Natom = Natom
        self.ele_list = ele_list
        self.q = q
        self.lattice_const = lattice_const
        self.lattice_inv = np.linalg.inv(lattice_const)

        # convert lattice constant to lattice parameter (a, b, c, alpha, beta, gamma)
        self.lattice_para = const2para(self.lattice_const)

        return

    def log_geom_info(self):

        logging.info('Number of atoms : {}'.format(self.Natom))
        logging.info('Element list : {}'.format( set(self.ele_list)) )
        logging.info('Lattice parameter (Angstrom and degree) : ')
        logging.info('   a={:8.3f}       b={:8.3f}      c={:8.3f}'.format(*self.lattice_para[:3]))
        logging.info('   alpha={:8.3f}   beta={:8.3f}   gamma={:8.3f}'.format(*self.lattice_para[3:]))
        logging.info('')

        return

    def read_geom(self):
        logging.info('Reading structure file : %s' % self.path)
        self.__check_exist()
        self.__choose_format()
        self.__read_val()
        
        return

##################################################################################

    def judge_mol(self, q=None, ele_list=None):
        if q is None: q = self.q
        if ele_list is None: ele_list = self.ele_list

        Natom = q.shape[-1]
        dis_mat = np.zeros([Natom, Natom])
        r_mat = np.zeros([Natom, Natom])
        r_list = [covr[i] for i in ele_list]
        for i in range(Natom):
            dis_mat[i, :] = np.linalg.norm(q[:, :] - q[:, i, None], axis=0)
            r_mat[i, :] += r_list
            r_mat[:, i] += r_list

        r_mat *= 1.15
        d_mat = np.add(dis_mat, -r_mat)

        mol = []
        for i in range(Natom):
            atom = [a for a, x in enumerate(d_mat[i, :]) if x < 0 and a != i] + [i]
            if len(atom) > 1:
                mol.append(atom)

        self.mol_list = find_mol_graph(mol)
        self.Nmol = len(self.mol_list)

        f = open('mol_list', 'w')
        for mol in self.mol_list:
            for atom in mol:
                f.write('{}, '.format(atom+1))
            f.write('\n')
        f.close()

        logging.info('Number of molecules : {}'.format(self.Nmol))
        logging.info('')

        return

########################################################################################################################

    def supercell(self, q=None, Nim=None, chg=None, check=False):
        '''
        supercell. Fractional coordinate is necessary.
        :param q:
        :param Nim:
        :return:
        '''
        if q is None: q = self.q
        if Nim is None: Nim = [1, 1, 1]
        if chg is None: chg = np.zeros(self.Natom)

        from .util import get_pbc_list
        Nx = get_pbc_list(Nim[0])
        Ny = get_pbc_list(Nim[1])
        Nz = get_pbc_list(Nim[2])

        q = np.dot(self.lattice_inv, q)
        q_all = q
        ele_list = self.ele_list
        chg_all = chg

        for x in Nx:
            for y in Ny:
                for z in Nz:
                    if [x, y, z] != [0, 0, 0]:
                        shift_vec = [x, y, z]
                        if check:
                            for atom in range(self.Natom):
                                q_new = q[:, atom] + shift_vec
                                q_check = np.add(q_all, -q_new[:, None])
                                q_check = np.sum(np.abs(q_check), axis=0)
                                if not np.min(q_check) < 1e-4:
                                    q_all = np.append(q_all, np.transpose([q_new]), axis=1)
                                    ele_list.append(self.ele_list[atom])
                                    chg_all = np.append(chg_all, chg[atom])
                        else:
                            q_new = np.add(q, np.array(shift_vec)[:, None])
                            q_all = np.append(q_all, q_new, axis=1)
                            ele_list.append(self.ele_list)
                            chg_all = np.append(chg_all, chg)

        q_all = np.dot(self.lattice_const, q_all)

        return q_all, ele_list, chg_all

    def exclude_q(self, q_super, q=None, chg=None):
        if q is None: q = self.q
        if chg is None: chg = np.zeros(self.Natom)

        Natom = list(q_super.shape)[-1]

        q_all = np.zeros([3,0])
        chg_all = []
        for atom in range(Natom):
            q_new = q_super[:, atom]
            q_check = np.add(q, -q_new[:, None])
            q_check = np.sum(np.abs(q_check), axis=0)
            # print(np.min(q_check))
            if not np.min(q_check) < 1e-4:
                q_all = np.append(q_all, np.transpose([q_new]), axis=1)
                chg_all = np.append(chg_all, chg[atom])

        return q_all, chg_all

    def supercell_cut(self, q=None, ele_list=None, r=1.5):
        if q is None: q = self.q
        if ele_list == None: ele_list = self.ele_list

        q = np.dot(self.lattice_inv, q)
        q -= 0.5
        Natom = q.shape[1]
        q_new = []
        e_new = []

        for i in range(Natom):
            if q[:,i].all() <= r:
                q_new.append(q[:,i])
                e_new.append(ele_list[i])

        q_new = np.transpose(q_new)
        q_new += 0.5
        q_new = np.dot(self.lattice_const, q_new)

        return q_new, e_new

    def super_judge(self):
        q_all, ele_list = self.supercell(Nim=[1,1,1])
        # q, e = self.supercell_cut(q=q_all, ele_list=ele_list, r=1.5)
        # self.judge_mol(q=q, ele_list=e)
        self.judge_mol(q=q_all, ele_list=ele_list)

        return

    def remove_image_mol(self, sym_list):

        return
