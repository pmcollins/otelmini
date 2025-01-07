import logging


def test_logging():
    logger = logging.getLogger('test')
    logger.debug('debug message')

