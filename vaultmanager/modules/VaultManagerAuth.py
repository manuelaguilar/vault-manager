import os
import logging
import yaml
from collections import OrderedDict
from collections import namedtuple

try:
    from lib.AuthMethods.AuthMethodLDAP import AuthMethodLDAP
    from lib.AuthMethods.AuthMethodAppRole import AuthMethodAppRole
    from lib.VaultClient import VaultClient
    from lib.VaultAuthMethod import VaultAuthMethod
    import lib.utils as utils
except ImportError:
    from vaultmanager.lib.AuthMethods.AuthMethodLDAP import AuthMethodLDAP
    from vaultmanager.lib.AuthMethods.AuthMethodAppRole import AuthMethodAppRole
    from vaultmanager.lib.VaultClient import VaultClient
    from vaultmanager.lib.VaultAuthMethod import VaultAuthMethod
    import vaultmanager.lib.utils as utils


class VaultManagerAuth:
    """
    Authentication module
    """
    logger = None
    base_logger = None
    subparser = None
    parsed_args = None
    arg_parser = None
    module_name = None
    conf = None
    vault_client = None
    local_auth_methods = None
    distant_auth_methods = None

    def __init__(self, base_logger=None):
        """
        :param base_logger: main class name
        :type base_logger: string
        :param subparsers: list of all subparsers
        :type subparsers: argparse.ArgumentParser.add_subparsers()
        """
        self.base_logger = base_logger
        if base_logger:
            self.logger = logging.getLogger(
                base_logger + "." + self.__class__.__name__)
        else:
            self.logger = logging.getLogger()
        self.logger.debug("Initializing VaultManagerAuth")

    def initialize_subparser(self, subparsers):
        """
        Add the subparser of this specific module to the list of all subparsers

        :param subparsers: list of all subparsers
        :type subparsers: argparse.ArgumentParser.add_subparsers()
        :return:
        """
        self.logger.debug("Initializing subparser")
        self.module_name = \
            self.__class__.__name__.replace("VaultManager", "").lower()
        self.subparser = subparsers.add_parser(
            self.module_name,
            help=self.module_name + ' management'
        )
        self.subparser.add_argument("--push", action='store_true',
                                    help="Push auth methods to Vault")
        self.subparser.set_defaults(module_name=self.module_name)

    def check_args_integrity(self):
        """
        Checking provided arguments integrity
        """
        self.logger.debug("Checking arguments integrity")
        args_false_count = [self.kwargs.push].count(False)
        args_none_count = [self.kwargs.push].count(None)
        no_args_count = args_false_count + args_none_count
        if no_args_count in [1]:
            self.logger.critical("you must specify a command")
            return False
        return True

    def read_configuration(self):
        """
        Read configuration file
        """
        self.logger.debug("Reading configuration")
        with open(os.path.join(self.kwargs.vault_config, "auth-methods.yml"),
                  'r') as fd:
            try:
                self.conf = yaml.safe_load(fd)
            except yaml.YAMLError as e:
                self.logger.critical("Impossible to load conf file: " + str(e))
                return False
        self.logger.debug("Read conf: " + str(self.conf))
        return True

    def get_distant_auth_methods(self):
        """
        Fetch distant auth methods
        """
        self.logger.debug("Fetching distant auth methods")
        self.distant_auth_methods = []
        raw = self.vault_client.auth_list()
        for auth_method in raw:
            self.distant_auth_methods.append(
                VaultAuthMethod(
                    type=raw[auth_method]["type"],
                    path=(raw[auth_method]["path"] if 'path' in raw[
                        auth_method] else auth_method),
                    description=raw[auth_method]["description"],
                    tuning=OrderedDict(
                        sorted(raw[auth_method]["config"].items()))
                )
            )
        self.logger.debug("Distant auth methods found")
        for elem in self.distant_auth_methods:
            self.logger.debug(elem)

    def get_local_auth_methods(self):
        """
        Fetch local auth methods
        """
        self.logger.debug("Fetching local auth methods")
        self.local_auth_methods = []
        for auth_method in self.conf["auth-methods"]:
            auth_config = None
            if "auth_config" in auth_method:
                auth_config = OrderedDict(
                    sorted(auth_method["auth_config"].items()))
            self.local_auth_methods.append(
                VaultAuthMethod(
                    type=auth_method["type"],
                    path=auth_method["path"],
                    description=auth_method["description"],
                    tuning=OrderedDict(sorted(auth_method["tuning"].items())),
                    auth_config=auth_config
                )
            )
        self.logger.debug("Local auth methods found")
        for elem in self.local_auth_methods:
            self.logger.debug(elem)

    def disable_distant_auth_methods(self):
        """
        Disable auth methods not found in conf
        """
        self.logger.debug("Disabling auth methods")
        for auth_method in self.distant_auth_methods:
            if auth_method not in self.local_auth_methods:
                self.logger.info("Disabling: " + str(auth_method))
                self.vault_client.auth_disable(auth_method.path)

    def enable_distant_auth_methods(self):
        """
        Enable auth methods found in conf
        """
        self.logger.debug("Enabling auth methods")
        for auth_method in self.local_auth_methods:
            if auth_method not in self.distant_auth_methods:
                self.logger.info("Enabling: " + str(auth_method))
                self.vault_client.auth_enable(
                    auth_type=auth_method.type,
                    path=auth_method.path,
                    description=auth_method.description
                )

    def tune_auth_method(self, local_auth_method, distant_auth_method):
        """
        Tune a auth method

        :param local_auth_method: Local auth method
        :type local_auth_method: VaultAuthMethod
        :param distant_auth_method: Distant auth method
        :type distant_auth_method: VaultAuthMethod
        """
        self.logger.debug("Local tuning for: " + local_auth_method.path)
        self.logger.debug("Description: " + local_auth_method.description)
        self.logger.debug("Hash: " + local_auth_method.get_tuning_hash())
        self.logger.debug("Tuning: " + str(local_auth_method.tuning))

        self.logger.debug("Distant tuning for: " + distant_auth_method.path)
        self.logger.debug("Description: " + distant_auth_method.description)
        self.logger.debug("Hash: " + distant_auth_method.get_tuning_hash())
        self.logger.debug("Tuning: " + str(distant_auth_method.tuning))
        self.vault_client.auth_tune(
            local_auth_method.path,
            default_lease_ttl=local_auth_method.tuning["default_lease_ttl"],
            max_lease_ttl=local_auth_method.tuning["max_lease_ttl"],
            description=local_auth_method.description
        )

    def find_auth_methods_to_tune(self):
        """
        Identify auth methods where a tuning is needed
        """
        self.logger.debug("Tuning auth methods")
        for distant_auth in self.distant_auth_methods:
            for local_auth in self.local_auth_methods:
                if distant_auth == local_auth:
                    distant_tuning_hash = distant_auth.get_tuning_hash()
                    local_tuning_hash = local_auth.get_tuning_hash()
                    self.logger.debug("Hashs for %s/" % distant_auth.path)
                    self.logger.debug("Local: " + local_tuning_hash)
                    self.logger.debug("Distant: " + distant_tuning_hash)
                    if distant_tuning_hash != local_tuning_hash:
                        self.logger.info("The auth method " + local_auth.path +
                                         " will be tuned")
                        self.tune_auth_method(local_auth, distant_auth)

    def auth_push(self):
        """
        Push auth methods configuration to Vault
        """
        self.logger.info("Pushing auth methods to Vault")
        self.read_configuration()
        self.get_distant_auth_methods()
        self.get_local_auth_methods()
        for auth_method in self.local_auth_methods:
            if auth_method in self.distant_auth_methods:
                self.logger.debug("Auth method remaining unchanged " +
                                  str(auth_method))
        if "auth-methods-deletion" in self.conf and \
           self.conf["auth-methods-deletion"]:
            self.disable_distant_auth_methods()
        self.enable_distant_auth_methods()
        self.get_distant_auth_methods()
        self.logger.info("Auth methods successfully pushed to Vault")
        self.logger.info("Tuning auth methods")
        self.find_auth_methods_to_tune()
        self.logger.info("Auth methods successfully tuned")
        self.logger.info("Setting up auth method specific configuration")
        for auth_method in self.local_auth_methods:
            auth_method_module = None
            if auth_method.auth_config:
                if auth_method.type == "ldap":
                    auth_method_module = AuthMethodLDAP(
                        self.base_logger,
                        auth_method.path,
                        auth_method.auth_config,
                        self.vault_client
                    )
                elif auth_method.type == "approle":
                    auth_method_module = AuthMethodAppRole(
                        self.base_logger,
                        auth_method.path,
                        auth_method.auth_config,
                        self.vault_client
                    )
            if auth_method_module:
                auth_method_module.auth_method_configuration()
            else:
                self.logger.debug("No specific auth method configuration")
        self.logger.info("Auth method specific configuration OK")

    def run(self, kwargs):
        """
        Module entry point

        :param kwargs: Arguments parsed
        :type kwargs: dict
        """
        # Convert kwargs to an Object with kwargs dict as class vars
        self.kwargs = namedtuple("KwArgs", kwargs.keys())(*kwargs.values())
        self.logger.debug("Module " + self.module_name + " started")
        if not self.check_args_integrity():
            self.subparser.print_help()
            return False
        missing_args = utils.keys_exists_in_dict(
            self.logger, dict(self.kwargs._asdict()),
            [{"key": "vault_addr", "exc": [None, '']},
             {"key": "vault_token", "exc": [None, False]},
             {"key": "vault_config", "exc": [None, False, '']}]
        )
        if len(missing_args):
            raise ValueError(
                "Following arguments are missing %s\n" % [
                    k['key'].replace("_", "-") for k in missing_args]
            )
        self.vault_client = VaultClient(
            self.base_logger,
            vault_addr=self.kwargs.vault_addr,
            dry=self.kwargs.dry_run,
            skip_tls=self.kwargs.skip_tls
        )
        self.vault_client.authenticate()
        if self.kwargs.push:
            self.auth_push()
