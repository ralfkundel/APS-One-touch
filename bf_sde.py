import getpass
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import constants
from common import create_symlinks, execute_cmd_n_get_output, get_env_var, \
    get_from_setting_dict, \
    get_sde_dir_name_in_tar, get_sde_home_absolute, get_sde_pkg_abs_path, \
    get_sde_profile_details, get_sde_profile_name, get_selected_profile_name, \
    set_env_var, validate_path_existence, \
    append_to_env_var, \
    dname, get_switch_model, execute_cmd, get_ref_bsp_abs_path, \
    get_aps_bsp_pkg_abs_path, release_dir, \
    execute_cmd_n_get_output_2, delete_files, get_path_relative_to_user_home, \
    get_from_advance_setting_dict
from drivers import load_and_verify_kernel_modules


def get_sde_build_flags():
    return get_sde_profile_details().get(constants.sde_build_flags_node)


def build_sde():
    sde_tar = tarfile.open(get_sde_pkg_abs_path())
    sde_home_absolute = get_sde_home_absolute()
    sde_build_flags = get_sde_build_flags()

    # Deletion is required otherwise moving the directories
    # in further steps might create issues.
    # And delete only when user have opted for not to resume build
    if sde_build_flags is not None and '-rb' not in sde_build_flags:
        try:
            print("Deleting previous installation at {}.".format(
                sde_home_absolute))
            os.system('sudo rm -rf {}'.format(sde_home_absolute))
        except FileNotFoundError:
            print('{} already deleted.'.format(sde_home_absolute))

    # Extract tar here i.e. in APS one touch directory
    sde_tar.extractall()
    # In case SDE home is configured in yaml other than this directory,
    # If both paths are same following line doesn't cause any problem.
    if not os.path.exists(sde_home_absolute):
        shutil.move(get_sde_dir_name_in_tar(), sde_home_absolute)
    sde_tar.close()
    os.chdir(sde_home_absolute)
    build_opt = "-up"
    p4studio_build_profile = get_from_setting_dict('BF SDE',
                                                   'p4studio_build_profile')

    if get_selected_profile_name() in [constants.stratum_hw_profile_name,
                                       constants.stratum_sim_profile_name]:
        p4studio_build_profile = 'stratum_profile'

    if p4studio_build_profile == "" or p4studio_build_profile is None:
        build_opt = ""
        p4studio_build_profile = ""

    sde_install_cmd = "./p4studio_build/p4studio_build.py {} {}".format(
        build_opt,
        p4studio_build_profile)

    if sde_build_flags is not None:
        for flag in sde_build_flags:
            if flag:
                sde_install_cmd += ' ' + flag
    else:
        print('No build flag will be used for BF_SDE build.')
    os.environ[
        constants.path_env_var_name] += os.pathsep + sde_home_absolute + \
                                        '/install/bin/'
    print('Building sde with command {}'.format(sde_install_cmd))
    os.system(sde_install_cmd)
    return True


def start_bf_switchd():
    # os.chdir(common.dname)
    print('Starting BF switchd.')
    set_sde_env_n_load_drivers()
    profile_name = get_sde_profile_name()

    if profile_name == constants.sde_sim_profile_name:
        # TODO Do something meaningful, Possibly launch tofino model in separate shell,
        # Currently This just an interrupt for user to start tofino model.
        input('Make sure that tofino-model is running?')

    p4_prog_name = get_from_setting_dict('BF SDE', 'p4_name')

    # LD_LIBRARY_PATH is set for ONLPv2 case, libs in install/lib folder are
    # not found there but this does not cause any harm for Ubuntu case either.
    # set_env('LD_LIBRARY_PATH', "/{0}/install/lib".format(get_env_var('SDE')))
    # print("LD_LIBRARY_PATH : ")
    # os.system("echo $LD_LIBRARY_PATH")

    if not p4_prog_name:
        print("Starting switchd without p4 program")
        start_switchd_cmd = "sudo {0}/install/bin/bf_switchd --install-dir {" \
                            "0}/install --conf-file {" \
                            "0}/pkgsrc/p4-examples/tofino/tofino_skip_p4.conf" \
                            ".in --skip-p4".format(get_env_var('SDE'))
        if profile_name == constants.sde_hw_profile_name:
            start_switchd_cmd = "sudo -E {0}/run_switchd.sh -c {" \
                                "0}/pkgsrc/p4-examples/tofino/tofino_skip_p4.conf.in --skip-p4".format(
                get_env_var('SDE'))
    else:
        print("Starting switchd with P4 prog:{}".format(p4_prog_name))
        start_switchd_cmd = 'sudo -E {0}/run_switchd.sh -p {1}'.format(
            get_env_var('SDE'),
            p4_prog_name.replace(".p4", ""))
    username = getpass.getuser()

    if username == "root":
        start_switchd_cmd = start_switchd_cmd.replace("sudo -E", "")
    alloc_dma()
    print("Starting switchd with command : {}".format(start_switchd_cmd))
    os.system(start_switchd_cmd)


def alloc_dma():
    output = execute_cmd_n_get_output('cat /etc/sysctl.conf')
    if 'vm.nr_hugepages = 128' not in output:
        print('Setting up huge pages...')
        dma_alloc_cmd = 'sudo /{}/pkgsrc/ptf-modules/ptf-utils/dma_setup.sh'.format(
            get_env_var('SDE'))
        os.system(dma_alloc_cmd)


def ask_user_for_building_sde():
    install_sde = input("SDE : build y/[n]?")
    if not install_sde:
        install_sde = "n"
    if install_sde == "y":
        create_symlinks()
        build_sde()
    else:
        print("You selected not to build SDE.")


diff_file = 'bf2556x_1t.diff'


def prepare_bsp_pkg():
    bsp_dev_abs = get_bsp_dev_abs_path()
    earliest_commit_hash = execute_cmd_n_get_output_2(
        'git --git-dir {0}/.git rev-list --max-parents=0 HEAD'.format(
            bsp_dev_abs))
    latest_commit_hash = execute_cmd_n_get_output_2(
        'git --git-dir {0}/.git rev-parse HEAD'.format(bsp_dev_abs))
    os.chdir(bsp_dev_abs)
    execute_cmd_n_get_output_2(
        'git --git-dir {0}/.git diff {1} {2} -- \':!./platforms/apsn/\' \':!.idea/\' \':!.gitignore\' > {3}'.
            format(bsp_dev_abs, earliest_commit_hash, latest_commit_hash,
                   bsp_dev_abs + '/' + diff_file))

    latest_commit_hash_short = execute_cmd_n_get_output_2(
        'git --git-dir {0}/.git rev-parse --short HEAD'.format(bsp_dev_abs))
    bsp_name = '/' + os.path.basename(bsp_dev_abs) \
               + '_' + latest_commit_hash_short
    bsp_rel_dir = release_dir + bsp_name

    try:
        os.mkdir(bsp_rel_dir)
        print('SAL release directory {} created.'.format(bsp_rel_dir))
    except FileExistsError:
        print('BSP Release directory {} already exists, recreated.'.format(
            bsp_rel_dir))
        delete_files(bsp_rel_dir)
        os.mkdir(bsp_rel_dir)

    shutil.move(bsp_dev_abs + '/' + diff_file, bsp_rel_dir + '/' + diff_file)
    shutil.copytree(bsp_dev_abs + '/platforms/apsn/', bsp_rel_dir + '/apsn')
    shutil.make_archive(bsp_rel_dir, 'zip', bsp_rel_dir)


def ask_user_for_building_bsp():
    if get_sde_profile_name() == constants.sde_hw_profile_name:
        in_put = input("BSP : build y/[n]?")
        if not in_put:
            in_put = "n"
        if in_put == "y":
            install_switch_bsp()
        if in_put == "p":
            prepare_bsp_pkg()


def ask_user_for_starting_sde():
    start_sde = input("SDE : start y/[n]?")
    if not start_sde:
        start_sde = "n"
    if start_sde == "y":
        start_bf_switchd()
    else:
        print("You selected not to start SDE.")


def load_bf_sde_profile():
    ask_user_for_building_sde()
    ask_user_for_building_bsp()
    prepare_sde_release()
    # SDE to be started only in case of SDE profiles
    # Else SDE will be started by either SAL or STRATUM
    if get_selected_profile_name() in [constants.sde_hw_profile_name,
                                       constants.sde_sim_profile_name]:
        ask_user_for_starting_sde()


def prepare_sde_release():
    # TODO prepare precompiled binaries from SDE, to avoid the need for
    #  building SDE.
    pass


def set_sde_env():
    print("Setting environment for BF_SDE.")
    sde_home_absolute = get_sde_home_absolute()
    if validate_path_existence(sde_home_absolute, 'SDE'):
        set_env_var(constants.sde_env_var_name, sde_home_absolute)
        set_env_var(constants.sde_install_env_var_name,
                    get_env_var(constants.sde_env_var_name) + '/install/')
        append_to_env_var(constants.path_env_var_name, get_env_var(
            constants.sde_install_env_var_name) + '/bin/')
        print(
            'Environment variables set: \n SDE: {0} \n SDE_INSTALL: {1} \n PATH: {2}'.format(
                get_env_var(constants.sde_env_var_name),
                get_env_var(constants.sde_install_env_var_name),
                get_env_var(constants.path_env_var_name)))
        return True
    else:
        print('ERROR: SDE directory couldnt be found, exiting .')
        exit(0)


def load_drivers():
    if get_sde_profile_name() == constants.sde_hw_profile_name:
        print('Loading kernel modules.')
        if not load_and_verify_kernel_modules():
            print("ERROR:Some kernel modules are not loaded.")
            exit(0)
    else:
        print('Running simulation, No need to load kernel modules.')


def set_sde_env_n_load_drivers():
    set_sde_env()
    load_drivers()
    return True


def install_switch_bsp():
    set_sde_env_n_load_drivers()
    aps_bsp_installation_file = get_aps_bsp_pkg_abs_path()
    print("Installing {}".format(aps_bsp_installation_file))
    aps_zip = zipfile.ZipFile(aps_bsp_installation_file)
    aps_zip.extractall(str(Path(aps_bsp_installation_file).parent))
    aps_bsp_dir = aps_zip.namelist()[0]
    aps_bsp_dir_absolute = str(
        Path(aps_bsp_installation_file).parent) + '/' + aps_bsp_dir
    aps_zip.close()

    ref_bsp_tar = tarfile.open(get_ref_bsp_abs_path())
    ref_bsp_tar.extractall(str(Path(get_ref_bsp_abs_path()).parent))
    ref_bsp_dir = ref_bsp_tar.getnames()[0]
    os.chdir(str(
        Path(get_ref_bsp_abs_path()).parent) + '/' + ref_bsp_dir + '/packages')
    pltfm_tar_name = ''
    for f in os.listdir('./'):
        if f.endswith('.tgz'):
            pltfm_tar_name = f
    pltfm_tar = tarfile.open(pltfm_tar_name)
    pltfm_tar.extractall()
    bf_pltfm_dir = str(Path(
        get_ref_bsp_abs_path()).parent) + '/' + ref_bsp_dir + '/packages/' + \
                   pltfm_tar.getnames()[0]

    aps_pltfm_dir = bf_pltfm_dir + '/platforms/apsn/'
    if os.path.exists(aps_pltfm_dir):
        shutil.rmtree(aps_pltfm_dir)

    shutil.copytree(aps_bsp_dir_absolute, aps_pltfm_dir)

    pltfm_tar.close()
    ref_bsp_tar.close()
    os.chdir(bf_pltfm_dir)
    os.system('patch -p1 < {0}/{1}'.format(str(
        Path(aps_bsp_installation_file).parent), diff_file))
    # os.environ['BSP'] = os.getcwd()
    # print("BSP home directory set to {}".format(os.environ['BSP']))
    os.environ['BSP_INSTALL'] = get_env_var('SDE_INSTALL')
    print(
        "BSP_INSTALL directory set to {}".format(
            os.environ['BSP_INSTALL']))

    os.system("autoreconf && autoconf")
    os.system("chmod +x ./autogen.sh")
    #os.system("chmod +x ./configure")
    if get_switch_model() == constants.bf2556x_1t:
        execute_cmd(
            "CFLAGS=-Wno-error ./configure --prefix={} --enable-thrift --with-tof-brgup-plat".format(
                os.environ['BSP_INSTALL']))
    else:
        execute_cmd(
            "CFLAGS=-Wno-error ./configure --prefix={} --enable-thrift".format(
                os.environ['BSP_INSTALL']))
    os.system("make")
    os.system("sudo make install")
    os.chdir(dname)
    return True


def just_load_sde():
    ask_user_for_building_sde()
    ask_user_for_building_bsp()
    prepare_sde_release()
    ask_user_for_starting_sde()


if __name__ == '__main__':
    just_load_sde()


def get_default_bsp_dev_path():
    if get_switch_model() == constants.bf2556x_1t:
        return get_path_relative_to_user_home(
            '/bsp/bf-reference-bsp-9.2.0-BF2556')
    elif get_switch_model() == constants.bf6064x_t:
        return get_path_relative_to_user_home(
            '/bsp/bf-reference-bsp-9.2.0-BF6064')
    else:
        print('Development BSp can\'t be retrieved for switch model'.
              format(get_switch_model()))


def get_bsp_dev_abs_path():
    path_from_adv_setting = get_from_advance_setting_dict(constants.BSP_node,
                                                          constants.bsp_dev_node_name)
    if path_from_adv_setting is None:
        return get_default_bsp_dev_path()
    else:
        return get_path_relative_to_user_home(path_from_adv_setting)
