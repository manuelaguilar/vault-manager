import os
import logging
try:
    from lib.VaultClient import VaultClient
except ImportError:
    from vaultmanager.lib.VaultClient import VaultClient


class VaultManagerKV:
    logger = None
    base_logger = None
    subparser = None
    parsed_args = None
    arg_parser = None
    module_name = None

    def __init__(self, base_logger, subparsers):
        """
        :param base_logger: main class name
        :type base_logger: string
        :param subparsers: list of all subparsers
        :type subparsers: argparse.ArgumentParser.add_subparsers()
        """
        self.base_logger = base_logger
        self.logger = logging.getLogger(base_logger + "." + self.__class__.__name__)
        self.logger.debug("Initializing VaultManagerKV")
        self.initialize_subparser(subparsers)

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
            self.module_name, help=self.module_name + ' management'
        )
        self.subparser.add_argument("--export", nargs=1,
                                    help="""export kv store from specified path
                                    PATH_TO_EXPORT from $VAULT_ADDR instance
                                    to $VAULT_TARGET_ADDR at the same path.
                                    $VAULT_TOKEN is used for $VAULT_ADDR and
                                    $VAULT_TARGET_TOKEN is used for 
                                    $VAULT_TARGET_ADDR""",
                                    metavar="PATH_TO_EXPORT")
        self.subparser.set_defaults(module_name=self.module_name)

    def check_env_vars(self):
        """
        Check if all needed env vars are set

        :return: bool
        """
        self.logger.debug("Checking env variables")
        needed_env_vars = ["VAULT_ADDR", "VAULT_TOKEN",
                           "VAULT_TARGET_ADDR", "VAULT_TARGET_TOKEN"]
        if not all(env_var in os.environ for env_var in needed_env_vars):
            self.logger.critical("The following env vars must be set")
            self.logger.critical(str(needed_env_vars))
            return False
        self.logger.debug("All env vars are set")
        self.logger.info("Vault address: " + os.environ["VAULT_ADDR"])
        return True

    def read_from_vault(self):
        """
        Read secret tree from Vault

        :return dict(dict)
        """
        self.logger.debug("Reading kv tree")
        vault_client = VaultClient(
            self.base_logger,
            dry=self.parsed_args.dry_run,
            skip_tls=self.parsed_args.skip_tls
        )
        vault_client.authenticate()
        self.logger.info("Exporting %s from %s to %s" %
                         (
                             self.parsed_args.export[0],
                             os.environ["VAULT_ADDR"],
                             os.environ["VAULT_TARGET_ADDR"]
                         )
                         )
        kv_full = {}
        kv_list = vault_client.get_secrets_tree(
            self.parsed_args.export[0]
        )
        self.logger.debug("Secrets found: " + str(kv_list))
        for kv in kv_list:
            kv_full[kv] = vault_client.read_secret(kv)
        return kv_full

    def push_to_vault(self, exported_kv):
        """
        Push exported kv to Vault

        :param exported_kv: Exported KV store
        :type exported_kv: dict
        """
        self.logger.debug("Pushing exported kv to Vault")
        vault_client = VaultClient(
            self.base_logger,
            dry=self.parsed_args.dry_run,
            vault_addr=os.environ["VAULT_TARGET_ADDR"],
            skip_tls=self.parsed_args.skip_tls
        )
        vault_client.authenticate(os.environ["VAULT_TARGET_TOKEN"])
        for secret in exported_kv:
            self.logger.debug("Exporting secret: " + secret)
            vault_client.write(secret, exported_kv[secret], hide_all=True)

    def run(self, arg_parser, parsed_args):
        """
        Module entry point

        :param arg_parser: Arguments parser instance
        :param parsed_args: Arguments parsed fir this module
        :type parsed_args: argparse.ArgumentParser.parse_args()
        """
        self.parsed_args = parsed_args
        self.arg_parser = arg_parser
        if not self.check_env_vars():
            return False
        if not self.parsed_args.export:
            self.logger.error("Only one parameter should be specified")
            self.subparser.print_help()
            return False
        self.logger.debug("Module " + self.module_name + " started")
        if self.parsed_args.export:
            exported_kv = self.read_from_vault()
            self.push_to_vault(exported_kv)



